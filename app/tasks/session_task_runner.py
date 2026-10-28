import asyncio
from datetime import timedelta, datetime
from sqlalchemy.orm import Session as DBSession
from app.models.db.session_log import SessionLog
from app.models.db.chat_message_model import ChatMessage
from app.utils.time_utils import get_kst_now


def check_and_close_expired_sessions_for_user(db: DBSession, user_id: int):
    now = get_kst_now()

    open_sessions = (
        db.query(SessionLog)
          .filter(SessionLog.user_id == user_id, SessionLog.end_time == None)
          .all()
    )

    for session in open_sessions:
        last_chat = (
            db.query(ChatMessage)
              .filter(
                  ChatMessage.session_id == session.session_id,
                  ChatMessage.user_id == user_id,
              )
              .order_by(ChatMessage.timestamp.desc())
              .first()
        )
        if not last_chat:
            continue

        # 20분 경과 시 세션 종료
        if now - last_chat.timestamp > timedelta(minutes=3):
            session.end_time = last_chat.timestamp + timedelta(minutes=3)
            db.commit()
            print(f"[✅ 세션 종료됨] user_id={user_id}, session_id={session.session_id}")


async def session_checker_all_users_loop():
    import logging
    from app.core.connection import SessionLocal
    logger = logging.getLogger(__name__)
    while True:
        # 매 회차 새 트랜잭션을 사용하고, 실패 후에도 다음 점검을 수행한다.
        with SessionLocal() as db:
            try:
                user_ids = (
                    db.query(SessionLog.user_id)
                      .filter(SessionLog.end_time == None)
                      .distinct()
                      .all()
                )
                for (user_id,) in user_ids:
                    check_and_close_expired_sessions_for_user(db, user_id)
            except Exception:
                db.rollback()
                logger.error("Session expiration check failed", exc_info=False)
        await asyncio.sleep(90)
