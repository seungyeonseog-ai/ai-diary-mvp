from app.config.settings import settings
import json
from sqlalchemy.orm import Session
from app.repositories.weekly_analysis_repository import WeeklyAnalysisRepository, SourceBatchConflict
from app.clients.gpt_api import call_gpt
from app.prompt.weekly_analysis_prompts import (
    emotion_trend_prompt,
    keyword_pattern_prompt,
    comprehensive_analysis_prompt
)
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class WeeklyAnalysisService:
    def __init__(self, db: Session):
        self.db = db

    def analyze_weekly_data(self, user_id: int):
        """원본 선택·저장에 짧은 전용 세션을 써서 AI 대기 중 DB를 점유하지 않는다."""
        # 호출자의 세션·미확정 변경에는 영향을 주지 않는다.
        try:
            with Session(bind=self.db.get_bind(), expire_on_commit=False) as read_db:
                repo = WeeklyAnalysisRepository(read_db)
                unused_reports = repo.get_unused_weekly_reports(user_id, 7)
                if len(unused_reports) < 7:
                    return None
                weekly_data = self._prepare_weekly_data(unused_reports)
                report_ids = [report.report_id for report in unused_reports]
                used_dates = [report.date_str for report in unused_reports]
                week_start = unused_reports[0].timestamp
                week_end = unused_reports[-1].timestamp
                if repo.has_saved_batch(user_id, week_start, week_end, used_dates, report_ids):
                    logger.warning("weekly_existing_batch_skipped user_id=%s", user_id)
                    return None
            # DB 세션을 닫은 상태에서 AI 분석 3단계를 실행한다.
            # 3-1. 감정 변화 분석
            emotion_result = self._analyze_emotion_trend(weekly_data)

            # 3-2. 키워드 패턴 분석
            keyword_result = self._analyze_keyword_pattern(weekly_data)

            # 3-3. 종합 분석
            comprehensive_result = self._analyze_comprehensive(
                emotion_result, keyword_result, weekly_data
            )

            # 4. 원본 사용 처리와 결과를 함께 커밋한다.
            with Session(bind=self.db.get_bind(), expire_on_commit=False) as write_db:
                analysis = WeeklyAnalysisRepository(write_db).save_weekly_analysis(
                    user_id=user_id,
                    week_start_date=week_start,
                    week_end_date=week_end,
                    used_dates=used_dates,
                    emotion_result=emotion_result,
                    keyword_result=keyword_result,
                    comprehensive_result=comprehensive_result,
                    report_ids=report_ids
                )
            logger.info("weekly_analysis_saved user_id=%s analysis_id=%s", user_id, analysis.analysis_id)
            self._run_followup(user_id, analysis.analysis_id)
            return analysis
        except SourceBatchConflict:
            logger.info("weekly_batch_already_consumed user_id=%s", user_id)
            return None
        except Exception as e:
            logger.error("weekly_analysis_failed user_id=%s error_type=%s", user_id, type(e).__name__)
            return None

    def _run_followup(self, user_id, analysis_id):
        if not settings.upper_reports_enabled:
            return
        # 비활성 상태에서는 모델/검색 서비스도 생성하지 않는다.
        try:
            from app.services.weekly_similar_flow_service import WeeklySimilarFlowService
            flow = WeeklySimilarFlowService()
            flow.run(user_id=user_id, analysis_id=analysis_id)
        except Exception as e:
            logger.warning("weekly_followup_failed user_id=%s error_type=%s", user_id, type(e).__name__)

    def _prepare_weekly_data(self, weekly_reports):
        """주간 데이터 준비"""
        weekly_emotions = [report.emotions for report in weekly_reports]
        weekly_scores = [report.scores for report in weekly_reports]
        weekly_keywords = [report.keywords for report in weekly_reports]
        weekly_summaries = [report.summary for report in weekly_reports]

        return {
            "weekly_emotions": weekly_emotions,
            "weekly_scores": weekly_scores,
            "weekly_keywords": weekly_keywords,
            "weekly_summaries": weekly_summaries
        }

    def _analyze_emotion_trend(self, weekly_data):
        """감정 변화 분석"""
        prompt = [
            {"role": "system", "content": "당신은 사용자 한명의 개인의 감정을 분석 전문가입니다. 정확한 JSON 형태로 응답해주세요."},
            {"role": "user", "content": emotion_trend_prompt.format(
                weekly_emotions=weekly_data["weekly_emotions"],
                weekly_scores=weekly_data["weekly_scores"]
            )}
        ]

        print(f"🔍 [DEBUG] 감정 변화 분석 프롬프트 전송")
        response = call_gpt(prompt)

        # 마크다운 코드 블록 제거 (```json, ```)
        cleaned_response = response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]  # ```json 제거
        if cleaned_response.startswith('```'):
            cleaned_response = cleaned_response[3:]   # ``` 제거
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]  # 끝의 ``` 제거

        cleaned_response = cleaned_response.strip()

        # JSON 파싱 예외 처리
        try:
            result = json.loads(cleaned_response)
            return result
        except json.JSONDecodeError as e:
            print(f"❌ [ERROR] 감정 변화 분석 JSON 파싱 실패: {e}")
            raise Exception(f"감정 변화 분석 GPT 응답이 유효한 JSON이 아닙니다: {e}")

    def _analyze_keyword_pattern(self, weekly_data):
        """키워드 패턴 분석"""
        prompt = [
            {"role": "system", "content": "당신은 사용자(한명,개인)의 키워드 분석 전문가입니다. 정확한 JSON 형태로 응답해주세요."},
            {"role": "user", "content": keyword_pattern_prompt.format(
                weekly_keywords=weekly_data["weekly_keywords"]
            )}
        ]

        print(f"🔍 [DEBUG] 키워드 패턴 분석 프롬프트 전송")
        response = call_gpt(prompt)

        # 마크다운 코드 블록 제거 (```json, ```)
        cleaned_response = response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]  # ```json 제거
        if cleaned_response.startswith('```'):
            cleaned_response = cleaned_response[3:]   # ``` 제거
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]  # 끝의 ``` 제거

        cleaned_response = cleaned_response.strip()

        # JSON 파싱 예외 처리
        try:
            result = json.loads(cleaned_response)
            return result
        except json.JSONDecodeError as e:
            print(f"❌ [ERROR] 키워드 패턴 분석 JSON 파싱 실패: {e}")
            raise Exception(f"키워드 패턴 분석 GPT 응답이 유효한 JSON이 아닙니다: {e}")

    def _analyze_comprehensive(self, emotion_result, keyword_result, weekly_data):
        """종합 분석"""
        prompt = [
            {"role": "system", "content": "당신은 사용자(한명,개인)의 심리를 분석 전문가입니다. 정확한 JSON 형태로 응답해주세요."},
            {"role": "user", "content": comprehensive_analysis_prompt.format(
                emotion_analysis=emotion_result,
                keyword_analysis=keyword_result,
                weekly_summaries=weekly_data["weekly_summaries"]
            )}
        ]

        print(f"🔍 [DEBUG] 종합 분석 프롬프트 전송")
        response = call_gpt(prompt)

        # 마크다운 코드 블록 제거 (```json, ```)
        cleaned_response = response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]  # ```json 제거
        if cleaned_response.startswith('```'):
            cleaned_response = cleaned_response[3:]   # ``` 제거
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]  # 끝의 ``` 제거

        cleaned_response = cleaned_response.strip()

        # JSON 파싱 예외 처리
        try:
            result = json.loads(cleaned_response)
            return result
        except json.JSONDecodeError as e:
            print(f"❌ [ERROR] 종합 분석 JSON 파싱 실패: {e}")
            raise Exception(f"종합 분석 GPT 응답이 유효한 JSON이 아닙니다: {e}")
