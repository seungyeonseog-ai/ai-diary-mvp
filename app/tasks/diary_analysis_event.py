from celery import shared_task
from sqlalchemy.orm import sessionmaker
from app.core.connection import engine
from app.services.weekly_analysis_service import WeeklyAnalysisService
from app.config.settings import settings
import redis
import json
import logging

logger = logging.getLogger(__name__)

SessionLocal = sessionmaker(bind=engine)
redis_client = redis.Redis(
    host=settings.redis_host, 
    port=settings.redis_port, 
    db=settings.redis_db
)


def run_weekly_analysis_and_notify(db, user_id, publish):
    """두 진입 경로가 같은 저장 정책을 쓰고, 커밋 완료된 결과만 알린다."""
    result = WeeklyAnalysisService(db).analyze_weekly_data(user_id)
    if result is None:
        return None
    message = {
        "type": "seven_day_report",
        "target": "study-section",
        "message": "7일 감정 레포트가 완성되었습니다!",
        "user_id": user_id,
        "analysis_id": result.analysis_id,
        "week_start_date": result.week_start_date.strftime("%m-%d"),
        "week_end_date": result.week_end_date.strftime("%m-%d")
    }
    publish(f"user_{user_id}_report", json.dumps(message))
    return result


@shared_task
def check_weekly_analysis_after_diary_save(user_id: int):
    """구형 저장 이벤트는 미사용7건 생성으로 돌아가지 않는다."""
    return {'status':'replaced_by_weekly_cycles'}
