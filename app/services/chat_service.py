from app.utils.time_utils import get_kst_now
from app.models.db.chat_message_model import ChatMessage
from sqlalchemy.orm import Session
from datetime import datetime


# 유저 메시지 저장 및 turn 계산
def save_user_message(db: Session, user_id: int, message: str, session_id: str) -> int:
    latest_turn = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id, ChatMessage.session_id == session_id)
        .order_by(ChatMessage.turn.desc())
        .first()
    )

    new_turn = latest_turn.turn + 1 if latest_turn else 1

    new_msg = ChatMessage(
        user_id=user_id,
        session_id=session_id,
        role="user",
        message=message,
        turn=new_turn,
                    timestamp=get_kst_now()  # 시스템 로컬 시간 사용 (KST)
    )

    db.add(new_msg)
    db.commit()

    print(f"🕒 현재 저장된 메시지 timestamp: {new_msg.timestamp}")
    print(f"📨 session_id: {session_id} / turn: {new_turn}")

    return new_turn



# GPT 응답 저장 (세션 ID 포함)
def save_gpt_response(
    db: Session,
    user_id: int,
    message: str,
    turn: int,
    session_id: str,        # 추가
):
    try:
        db.add(ChatMessage(
            user_id=user_id,
            role="assistant",
            message=message,
            turn=turn,
            session_id=session_id,  # 모델의 컬럼으로 지정
            timestamp=get_kst_now()  # 시스템 로컬 시간 사용 (KST)
        ))
        db.commit()
        print(f"✅ GPT 응답 저장 완료 - user_id: {user_id}, turn: {turn}")
    except Exception as e:
        print(f"❌ GPT 응답 저장 실패: {type(e).__name__}")
        db.rollback()
        raise e
