"""서재 복원용 읽기 전용 상태. AI 생성이나 읽음 처리를 실행하지 않는다."""
from datetime import datetime, timedelta
from app.models.db.chat_message_model import ChatMessage
from app.models.db.study_model import (
    DiaryReport, EncouragementReport, WeeklyAnalysisReport, DiaryAnalysisReport)
from app.utils.time_utils import KST, get_kst_now


def today_encouragement(db, user_id, now):
    start = datetime.combine(now.date(), datetime.min.time())
    return db.query(EncouragementReport).filter(
        EncouragementReport.user_id == user_id,
        EncouragementReport.timestamp >= start,
        EncouragementReport.timestamp < start + timedelta(days=1)
    ).order_by(EncouragementReport.timestamp.desc(), EncouragementReport.encouragement_id.desc()).first()


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
        DiaryReport.timestamp >= start, DiaryReport.timestamp < end
    ).first()
    unused = db.query(DiaryAnalysisReport).filter(
        DiaryAnalysisReport.user_id == user_id,
        DiaryAnalysisReport.is_used_in_weekly == False
    ).count()
    letter_state = 'ready' if letter else (
        'insufficient' if words < 100 else 'waiting_time' if now.hour < 10 else 'pending')
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
            'state': 'ready' if weekly else 'pending' if unused >= 7 else 'insufficient',
            'analysis_id': weekly.analysis_id if weekly else None,
        }
    }
