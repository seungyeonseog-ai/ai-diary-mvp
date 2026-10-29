from app.utils.time_utils import get_kst_now
from sqlalchemy.orm import Session
from app.models.db.study_model import DiaryAnalysisReport, WeeklyAnalysisReport
from app.models.db.chat_message_model import ChatMessage
from app.models.db.user_model import User
from datetime import datetime, timedelta
from sqlalchemy import func
from collections import Counter
import json

SOURCE_IDS_KEY = "_source_report_ids"


class SourceBatchConflict(Exception):
    """다른 작업이 이미 입력 일부/전체를 사용했으므로 이번 결과는 저장하지 않는다."""


class SourceResolutionError(Exception):
    """과거 결과의 원본을 정확하게 특정할 수 없다."""


class WeeklyAnalysisRepository:
    def __init__(self, db: Session):
        self.db = db
    
    # def get_weekly_reports(self, user_id: int, days: int = 7):
    #     """최근 N일간의 일일 분석 리포트 조회"""
    #     end_date = get_kst_now()  # 시스템 로컬 시간 사용 (KST)
    #     start_date = end_date - timedelta(days=days)
        
    #     reports = self.db.query(DiaryAnalysisReport).filter(
    #         DiaryAnalysisReport.user_id == user_id,
    #         DiaryAnalysisReport.timestamp >= start_date,
    #         DiaryAnalysisReport.timestamp <= end_date
    #     ).order_by(DiaryAnalysisReport.timestamp.asc()).all()
        
    #     return reports
    
    def get_unused_weekly_reports(self, user_id: int, days: int = 7):
        """사용되지 않은 일일 분석 리포트 조회 (날짜순 정렬)"""
        unused_reports = self.db.query(DiaryAnalysisReport).filter(
            DiaryAnalysisReport.user_id == user_id,
            DiaryAnalysisReport.is_used_in_weekly == False
        ).order_by(DiaryAnalysisReport.timestamp.asc(), DiaryAnalysisReport.report_id.asc()).limit(days).all()
        
        return unused_reports
    
    def get_users_with_unused_reports(self, days: int = 7):
        """7일치 미사용 리포트가 있는 사용자들 조회"""
        # 서브쿼리로 7일치 미사용 리포트가 있는 사용자 ID 조회
        subquery = self.db.query(DiaryAnalysisReport.user_id).filter(
            DiaryAnalysisReport.is_used_in_weekly == False
        ).group_by(DiaryAnalysisReport.user_id).having(
            func.count(DiaryAnalysisReport.report_id) >= days
        )
        
        return self.db.query(User).filter(User.id.in_(subquery)).all()
    
    def check_weekly_analysis_exists(self, user_id: int, week_start_date: datetime) -> bool:
        """해당 주의 주간 분석이 이미 존재하는지 확인 (start_date 기준)"""
        return self.db.query(WeeklyAnalysisReport).filter(
            WeeklyAnalysisReport.user_id == user_id,
            WeeklyAnalysisReport.week_start_date == week_start_date
        ).first() is not None
    
    def get_analysis_sources(self, analysis):
        """새 결과는 실제 ID, 과거 결과는 모호하지 않은 used_dates만 사용한다."""
        result = analysis.comprehensive_pattern_result
        if isinstance(result, dict) and SOURCE_IDS_KEY in result:
            ids = result[SOURCE_IDS_KEY]
            if (not isinstance(ids, list) or len(ids) != 7 or
                    any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != 7):
                raise SourceResolutionError()
            rows = self.db.query(DiaryAnalysisReport).filter(
                DiaryAnalysisReport.user_id == analysis.user_id,
                DiaryAnalysisReport.report_id.in_(ids)
            ).all()
            if len(rows) != len(ids):
                raise SourceResolutionError()
            by_id = {row.report_id: row for row in rows}
            return [by_id[i] for i in ids]

        dates = analysis.used_dates
        if isinstance(dates, str):
            try:
                dates = json.loads(dates)
            except (ValueError, TypeError):
                raise SourceResolutionError() from None
        if not isinstance(dates, list) or not dates or any(not isinstance(d, str) for d in dates):
            raise SourceResolutionError()
        rows = self.db.query(DiaryAnalysisReport).filter(
            DiaryAnalysisReport.user_id == analysis.user_id,
            DiaryAnalysisReport.date_str.in_(dates)
        ).order_by(DiaryAnalysisReport.timestamp.asc(), DiaryAnalysisReport.report_id.asc()).all()
        # 같은 날짜의 후보가 더 많으면 어떤 행이 실제 입력이었는지 추측하지 않는다.
        if Counter(row.date_str for row in rows) != Counter(dates):
            raise SourceResolutionError()
        return rows

    def has_saved_batch(self, user_id, week_start, week_end, dates, report_ids):
        """기존 결과·부분 저장 의심 배치를 새 작업이 자동 재생성하지 않게 한다."""
        rows = self.db.query(WeeklyAnalysisReport).filter(
            WeeklyAnalysisReport.user_id == user_id,
            WeeklyAnalysisReport.week_start_date == week_start,
            WeeklyAnalysisReport.week_end_date == week_end
        ).all()
        for row in rows:
            if isinstance(row.comprehensive_pattern_result, dict) and SOURCE_IDS_KEY in row.comprehensive_pattern_result:
                old_ids = row.comprehensive_pattern_result[SOURCE_IDS_KEY]
                if isinstance(old_ids, list) and old_ids == report_ids:
                    return True
                continue
            old_dates = row.used_dates
            try:
                if isinstance(old_dates, str):
                    old_dates = json.loads(old_dates)
                if not isinstance(old_dates, list) or Counter(old_dates) == Counter(dates):
                    return True
            except (ValueError, TypeError):
                # 같은 범위인데 메타데이터가 손상됐다면 새 결과를 임의로 덧붙이지 않는다.
                return True
        return False
    
    # def exists_weekly_analysis(self, user_id: int, week_start_date: str) -> bool:
    #     """해당 주의 주간 분석이 있는지 확인"""
    #     return self.db.query(WeeklyAnalysisReport).filter(
    #         WeeklyAnalysisReport.user_id == user_id,
    #         WeeklyAnalysisReport.week_start_date == week_start_date
    #     ).first() is not None
    
    def save_weekly_analysis(self, user_id: int, week_start_date: datetime, 
                           week_end_date: datetime, used_dates: list,
                           emotion_result: dict, keyword_result: dict, 
                           comprehensive_result: dict, report_ids: list):
                           
        """입력 7건 선점과 결과 저장을 한 트랜잭션으로 처리한다. AI 호출은 바깥에서 한다."""
        if len(report_ids) != 7 or len(set(report_ids)) != 7 or len(used_dates) != 7:
            raise ValueError("Weekly analysis requires seven distinct source IDs")
        if not all(isinstance(value, dict) for value in (emotion_result, keyword_result, comprehensive_result)):
            raise ValueError("Weekly analysis results must be objects")
        try:
            # 조건부 UPDATE가 DB 쓰기 잠금을 잡는다. 동시 작업은 대기 후 false 조건을 다시 검사한다.
            claimed = self.db.query(DiaryAnalysisReport).filter(
                DiaryAnalysisReport.user_id == user_id,
                DiaryAnalysisReport.report_id.in_(report_ids),
                DiaryAnalysisReport.is_used_in_weekly == False
            ).update({"is_used_in_weekly": True}, synchronize_session=False)
            if claimed != 7:
                raise SourceBatchConflict()
            analysis = self._add_weekly_analysis(
                user_id, week_start_date, week_end_date, used_dates,
                emotion_result, keyword_result,
                {**comprehensive_result, SOURCE_IDS_KEY: list(report_ids)}
            )
            self.db.commit()
            return analysis
        except Exception:
            self.db.rollback()
            raise

    def _add_weekly_analysis(self, user_id, week_start_date, week_end_date, used_dates,
                             emotion_result, keyword_result, comprehensive_result):
        analysis = WeeklyAnalysisReport(
            user_id=user_id,
            week_start_date=week_start_date,
            week_end_date=week_end_date,
            used_dates=used_dates,
            emotion_trend_result=emotion_result,
            keyword_pattern_result=keyword_result,
            comprehensive_pattern_result=comprehensive_result,
            timestamp=get_kst_now()  # 시스템 로컬 시간 사용 (KST)
        )
        self.db.add(analysis)
        self.db.flush()
        return analysis 

    def session_id_chats(self, user_id: int, session_id: str) -> list[str]:
        """
        특정 user_id + session_id의 user 메시지만 수집하여 formatted_chats 스타일로 반환.
        포맷: 'user: {message}'
        정렬: turn ASC, 보조로 timestamp ASC
        """
        rows = (
            self.db.query(ChatMessage)
            .filter(
                ChatMessage.user_id == user_id,
                ChatMessage.session_id == session_id,
                ChatMessage.role == "user",
            )
            .order_by(ChatMessage.turn.asc(), ChatMessage.timestamp.asc())
            .all()
        )

        formatted_chats: list[str] = []
        for chat in rows:
            formatted_chats.append(f"{chat.role}: {chat.message}")

        return formatted_chats
