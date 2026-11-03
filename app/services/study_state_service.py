"""서재 복원용 읽기 전용 상태. AI 생성이나 읽음 처리를 실행하지 않는다."""
from datetime import datetime, timedelta
from app.models.db.chat_message_model import ChatMessage
from app.models.db.study_model import (
    DiaryReport, EncouragementReport, WeeklyAnalysisReport, DiaryAnalysisReport)
from app.utils.time_utils import KST, get_kst_now
from app.models.db.daily_model import LetterDelivery, DailyJob, DailySettings
from app.services.daily_service import current_hour
from app.services.weekly_cycle_service import status as cycle_status


def today_encouragement(db, user_id, now):
    start = datetime.combine(now.date(), datetime.min.time())
    row = db.query(EncouragementReport).filter(
        EncouragementReport.user_id == user_id,
        EncouragementReport.timestamp >= start,
        EncouragementReport.timestamp < start + timedelta(days=1)
    ).order_by(EncouragementReport.timestamp.desc(), EncouragementReport.encouragement_id.desc()).first()
    delivery = db.get(LetterDelivery,row.encouragement_id) if row else None
    return None if delivery and delivery.discarded else row


def latest_weekly(db, user_id):
    return db.query(WeeklyAnalysisReport).filter(
        WeeklyAnalysisReport.user_id == user_id
    ).order_by(WeeklyAnalysisReport.timestamp.desc(), WeeklyAnalysisReport.analysis_id.desc()).first()


def study_status(db, user_id):
    now = get_kst_now()
    start = datetime.combine(now.date(), datetime.min.time())
    end = start + timedelta(days=1)
    words = sum(len((row.message or '').split()) for row in db.query(ChatMessage).filter(
        ChatMessage.user_id == user_id, ChatMessage.role == 'user',
        ChatMessage.timestamp >= start, ChatMessage.timestamp < end
    ).all())
    letter = today_encouragement(db, user_id, now)
    weekly = latest_weekly(db, user_id)
    ai_diary = db.query(DiaryReport).filter(
        DiaryReport.user_id == user_id, DiaryReport.source_type == 'ai',
        DiaryReport.state == 'saved',
        DiaryReport.timestamp >= start, DiaryReport.timestamp < end
    ).first()
    cycle=cycle_status(db,user_id,now)
    day=now.date().isoformat()
    pref=db.get(DailySettings,user_id)
    hour=current_hour(pref,day) if pref else 22
    job=db.get(DailyJob,f'{user_id}:{day}:encouragement')
    letter_state = 'ready' if letter else 'skipped' if job and job.state=='skipped' else (
        'discarded' if job and job.letter_done else 'waiting_time' if now.hour<hour else 'pending')
    return {
        'user_id': user_id,
        'server_date': now.date().isoformat(),
        'server_now': now.replace(tzinfo=KST).isoformat(),
        'diary': {'available': not ai_diary and words >= 55,
                  'state': 'saved' if ai_diary else 'ready' if words >= 55 else 'insufficient'},
        'encouragement': {
            'state': letter_state,
            'id': letter.encouragement_id if letter else None,
            'date': letter.timestamp.date().isoformat() if letter else None,
        },
        'weekly': {
            'state': 'ready' if weekly else 'pending' if cycle['state']=='retry' else 'insufficient',
            'analysis_id': weekly.analysis_id if weekly else None,
            'cycle':cycle,
        }
    }
