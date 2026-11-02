from app.utils.time_utils import get_kst_now, KST
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.api.dependencies.auth_dependencies import get_current_user
from app.services.diary_service import DiaryService
from app.services.encourage_diary_service import EncourageDiaryService
from app.repositories.today_chat_message_repository import TodayChatMessageRepository
from app.models.schemas.study_schema import DiaryResponse, ManualDiaryInput
from app.services.manual_diary_service import save_manual_diary, ManualDiaryAlreadyExists
from app.models.db.user_model import User
from app.models.db.study_model import DiaryReport, EncouragementReport, WeeklyAnalysisReport, DiaryAnalysisReport
from app.core.connection import get_db
from sqlalchemy.orm import Session
from datetime import datetime, date
import json
import redis
import logging
from app.config.settings import settings
from sqlalchemy import func
from app.repositories.weekly_analysis_repository import WeeklyAnalysisRepository, SourceResolutionError

from app.services.study_state_service import study_status, today_encouragement, latest_weekly

router = APIRouter(prefix="/study", tags=["study"])
from app.api.dependencies.writing_dependencies import require_legacy_creation
logger = logging.getLogger(__name__)

# 일기 생성 스트리밍 라우터 -- sub diary generat 버튼이랑 호출출
@router.post("/diary/generate/stream", dependencies=[Depends(require_legacy_creation)])
async def generate_diary_stream(
    current_user: User = Depends(get_current_user),
    diary_service: DiaryService = Depends()
):
    try:
        # Repository 직접 호출
        chat_repository = TodayChatMessageRepository()

        # 오늘 AI 생성 여부 확인 (source_type='ai')
        today_ai_diary = chat_repository.check_today_diary_by_source(current_user.id, 'ai')
        if today_ai_diary:
            raise HTTPException(
                status_code=400,
                detail="오늘 이미 AI로 생성한 일기가 있습니다."
            )

        # 오늘 사용자 채팅 토큰수 확인
        formatted_chats, total_tokens = chat_repository.diary_get_today_user_chat_and_tokens(current_user.id)
        min_tokens = 55  # 최소 토큰수 설정
        if total_tokens < min_tokens:
            raise HTTPException(
                status_code=400,
                detail=f"일기 생성하기엔 오늘의 채팅수가 부족합니다"
            )

        return StreamingResponse(
            diary_service.generate_diary_stream(current_user.id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except HTTPException:
        # HTTPException은 그대로 전달
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"일기 생성 실패: {str(e)}")


# async def generate_diary_stream(
#     current_user: User = Depends(get_current_user),
#     diary_service: DiaryService = Depends()
# ):
#     try:
#         # Repository 직접 호출
#         chat_repository = TodayChatMessageRepository()

#         # 오늘 AI 생성 여부 확인 (source_type='ai')
#         today_ai_diary = chat_repository.check_today_diary_by_source(current_user.id, 'ai')
#         if today_ai_diary:
#             raise HTTPException(
#                 status_code=400,
#                 detail="오늘 이미 AI로 생성한 일기가 있습니다."
#             )

#         # 오늘 사용자 채팅 토큰 수 확인
#         combined_content, total_tokens = chat_repository.get_today_user_chat_content_and_tokens(current_user.id)
#         min_tokens = 55  # 최소 토큰 수 설정
#         if total_tokens < min_tokens:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"일기 생성하기엔 오늘의 채팅 토큰이 부족합니다 (현재: {total_tokens}개, 필요: {min_tokens}개)"
#             )

#         return StreamingResponse(
#             diary_service.generate_diary_stream(current_user.id),
#             media_type="text/plain"
#         )
#     except HTTPException:
#         # HTTPException은 그대로 전달
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"일기 생성 실패: {str(e)}")




















# 사용자 직접 일기 저장 라우터
@router.post("/user/diary/save", dependencies=[Depends(require_legacy_creation)])
def save_user_diary(
    diary_data: ManualDiaryInput,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = save_manual_diary(db.get_bind(), current_user.id, diary_data.content)
        return {"message": "일기가 성공적으로 저장되었습니다.", "diary_id": row.diary_id}
    except ManualDiaryAlreadyExists:
        raise HTTPException(status_code=409, detail="오늘 이미 직접 작성한 일기가 있습니다.")
    except Exception as e:
        logger.error("manual_diary_save_failed error_type=%s", type(e).__name__)
        raise HTTPException(status_code=500, detail="일기를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")


# 일기 생성 조건 체크 라우터
@router.get("/diary/check-condition")
async def check_diary_condition(
    current_user: User = Depends(get_current_user)
):
    try:
        # Repository 직접 호출
        chat_repository = TodayChatMessageRepository()

        # 오늘 AI 생성 여부 확인 (source_type='ai')
        today_ai_diary = chat_repository.check_today_diary_by_source(current_user.id, 'ai')
        if today_ai_diary:
            return {
                "available": False,
                "reason": "오늘 이미 AI로 생성한 일기가 있습니다."
            }

        # 오늘 사용자 채팅 토큰수 확인
        formatted_chats, total_tokens = chat_repository.diary_get_today_user_chat_and_tokens(current_user.id)
        min_tokens = 55  # 최소 토큰수 설정
        if total_tokens < min_tokens:
            return {
                "available": False,
                "reason": f"일기 생성하기엔 오늘의 채팅수가 부족합니다."
            }

        return {
            "available": True,
            "reason": "일기 생성이 가능합니다."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"조건 확인 실패: {str(e)}")




# async def check_diary_condition(
#     current_user: User = Depends(get_current_user)
# ):
#     try:
#         # Repository 직접 호출
#         chat_repository = TodayChatMessageRepository()

#         # 오늘 AI 생성 여부 확인 (source_type='ai')
#         today_ai_diary = chat_repository.check_today_diary_by_source(current_user.id, 'ai')
#         if today_ai_diary:
#             return {
#                 "available": False,
#                 "reason": "오늘 이미 AI로 생성한 일기가 있습니다."
#             }

#         # 오늘 사용자 채팅 토큰 수 확인
#         combined_content, total_tokens = chat_repository.get_today_user_chat_content_and_tokens(current_user.id)
#         min_tokens = 55  # 최소 토큰 수 설정
#         if total_tokens < min_tokens:
#             return {
#                 "available": False,
#                 "reason": f"일기 생성하기엔 오늘의 채팅 토큰이 부족합니다. (현재: {total_tokens}개, 필요: {min_tokens}개)"
#             }

#         return {
#             "available": True,
#             "reason": "일기 생성이 가능합니다."
#         }

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"조건 확인 실패: {str(e)}")




# 일기 목록 조회 라우터
@router.get("/diary/list")
async def get_diary_list(
    current_user: User = Depends(get_current_user)
):
    try:
        # Repository 직접 호출
        chat_repository = TodayChatMessageRepository()

        # 사용자의 모든 일기 조회 (최신순)
        diaries = chat_repository.get_user_diaries(current_user.id)

        # JS에서 기대하는 형태로 변환
        diary_list = []
        for diary in diaries:
            diary_list.append({
                "id": diary.diary_id,  # primary key는 diary_id
                "content": diary.content,
                "source_type": diary.source_type,  # 'user' 또는 'ai'
                "timestamp": diary.timestamp.isoformat() if diary.timestamp else None,
                "user_id": diary.user_id
            })

        return diary_list

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"일기 목록 조회 실패: {str(e)}")

# 개별 일기 조회 라우터
@router.get("/diary/{diary_id}")
async def get_diary_detail(
    diary_id: int,
    current_user: User = Depends(get_current_user)
):
    try:
        # Repository 직접 호출
        chat_repository = TodayChatMessageRepository()

        # 특정 일기 조회 (사용자 본인의 일기만)
        diary = chat_repository.get_diary_by_id(diary_id, current_user.id)

        if not diary:
            raise HTTPException(
                status_code=404,
                detail="일기를 찾을 수 없습니다."
            )

        # JS에서 기대하는 형태로 변환
        return {
            "id": diary.diary_id,
            "content": diary.content,
            "source_type": diary.source_type,
            "timestamp": diary.timestamp.isoformat() if diary.timestamp else None,
            "user_id": diary.user_id
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"일기 조회 실패: {str(e)}")


@router.get("/status")
async def get_study_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return study_status(db, current_user.id)
    except Exception as e:
        logger.error("study_status_failed user_id=%s error_type=%s", current_user.id, type(e).__name__)
        raise HTTPException(status_code=500, detail="서재 상태를 불러오지 못했습니다.") from None


@router.get("/encourage/check-condition")
async def check_encourage_condition(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    status = await get_study_status(current_user, db)
    letter = status['encouragement']
    reasons = {
        'ready': '오늘의 응원 편지를 확인할 수 있습니다.',
        'pending': '응원 편지 생성을 기다리고 있습니다.',
        'waiting_time': '응원 편지는 오전 10시 이후 생성됩니다.',
        'insufficient': '오늘 응원 메시지 생성하기엔 채팅이 부족합니다.'
    }
    return {**letter, 'available': letter['state'] == 'ready',
            'server_date': status['server_date'], 'reason': reasons[letter['state']]}


@router.get("/encourage")
async def get_today_encouragement(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        now = get_kst_now()
        letter = today_encouragement(db, current_user.id, now)
        if letter is None:
            raise HTTPException(status_code=404, detail="오늘의 응원 메시지가 없습니다.")
        response = {'encourage_content': letter.encourage_content,
                    'id': letter.encouragement_id, 'date': letter.timestamp.date().isoformat(),
                    'timestamp': letter.timestamp.replace(tzinfo=KST).isoformat(),
                    'server_date': now.date().isoformat()}
        try:
            client = redis.Redis(host=settings.redis_host, port=settings.redis_port, db=settings.redis_db,
                                 socket_connect_timeout=3, socket_timeout=3)
            client.publish(f"user_{current_user.id}_encourage", json.dumps({
                'type': 'encourage_unavailable', 'target': 'letter-overlay-glow',
                'message': '응원 편지 확인함', 'date': response['date'], 'result_id': letter.encouragement_id
            }))
        except Exception as e:
            logger.warning("encouragement_ack_failed user_id=%s error_type=%s", current_user.id, type(e).__name__)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error("encouragement_read_failed user_id=%s error_type=%s", current_user.id, type(e).__name__)
        raise HTTPException(status_code=500, detail="응원 편지를 불러오지 못했습니다.") from None


@router.get("/weekly/latest")
async def get_latest_weekly_report(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        report = latest_weekly(db, current_user.id)
        if report is None:
            raise HTTPException(status_code=404, detail="아직 저장된 주간 분석이 없습니다.")
        return await get_seven_day_report(report.analysis_id, current_user, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("weekly_latest_failed user_id=%s error_type=%s", current_user.id, type(e).__name__)
        raise HTTPException(status_code=500, detail="주간 분석을 불러오지 못했습니다.") from None


# 7일 감정 리포트 데이터 조회
@router.get("/seven-day-report/{analysis_id}")
async def get_seven_day_report(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        print(f"📊 7일 리포트 데이터 조회 시작: analysis_id={analysis_id}, user_id={current_user.id}")

        # weekly_analysis_report 테이블에서 데이터 조회
        weekly_data = db.query(WeeklyAnalysisReport).filter(
            WeeklyAnalysisReport.analysis_id == analysis_id,
            WeeklyAnalysisReport.user_id == current_user.id
        ).first()

        if not weekly_data:
            raise HTTPException(status_code=404, detail="7일 리포트 데이터를 찾을 수 없습니다.")

        print(f"🔍 weekly_data 조회 성공: week_start_date={weekly_data.week_start_date}, week_end_date={weekly_data.week_end_date}")

        # 분석 당시 실제 입력만 반환한다. 과거 결과는 모호하지 않은 날짜 집합과 호환한다.
        diary_data = WeeklyAnalysisRepository(db).get_analysis_sources(weekly_data)


        # 응답 데이터 구성
        response_data = {
            "weekly_analysis": {
                "id": weekly_data.analysis_id,
                "start_date": weekly_data.week_start_date.strftime("%m-%d"),
                "end_date": weekly_data.week_end_date.strftime("%m-%d"),
                "emotion_trend": weekly_data.emotion_trend_result,
                "keyword_patterns": weekly_data.keyword_pattern_result,
                "comprehensive_pattern_result": weekly_data.comprehensive_pattern_result,
                "overall_assessment": weekly_data.comprehensive_pattern_result.get("overall_assessment", "분석 중") if weekly_data.comprehensive_pattern_result else "분석 중"
            },
            "diary_analyses": [
                {
                    "id": diary.report_id,
                    "date_str": diary.date_str,
                    "emotions": diary.emotions,
                    "scores": diary.scores,
                    "keywords": diary.keywords,
                    "keyword_descriptions": diary.keyword_descriptions,
                    "summary": diary.summary
                }
                for diary in diary_data
            ]
        }

        logger.info("weekly_report_read analysis_id=%s user_id=%s count=%s",
                    analysis_id, current_user.id, len(diary_data))
        return response_data

    except HTTPException:
        raise
    except SourceResolutionError:
        logger.warning("weekly_report_sources_unresolved analysis_id=%s user_id=%s",
                       analysis_id, current_user.id)
        raise HTTPException(status_code=409, detail="주간 분석의 원본 자료를 정확히 확인할 수 없습니다.") from None
    except Exception as e:
        # 예외 본문에는 SQL 파라미터·개인 원문이 포함될 수 있다.
        logger.error("weekly_report_read_failed analysis_id=%s user_id=%s error_type=%s",
                     analysis_id, current_user.id, type(e).__name__)
        raise HTTPException(status_code=500, detail="7일 리포트 데이터 조회에 실패했습니다.") from None


# 차트 로딩 완료 알림
@router.post("/chart-loading-complete")
async def chart_loading_complete(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    try:

        # Redis에 구독 발행 (study/section.js가 받을 알림)
        redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db
        )

        message = {
            "type": "chart_loading_complete",
            "target": "study-section",
            "message": "7일 리포트 차트 로딩이 완료되었습니다.",
            "analysis_id": data.get("analysis_id"),
            "week_start_date": data.get("week_start_date"),
            "week_end_date": data.get("week_end_date")
        }

        channel = f"user_{current_user.id}_chart"
        message_json = json.dumps(message)

        print(f"📤 Redis 발행: channel={channel}, message={message_json}")
        result = redis_client.publish(channel, message_json)

        return {"status": "success", "message": "차트 로딩 완료 알림이 전송되었습니다."}

    except Exception as e:
        print(f"❌ 차트 로딩 완료 알림 전송 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=f"차트 로딩 완료 알림 전송 실패: {str(e)}")
