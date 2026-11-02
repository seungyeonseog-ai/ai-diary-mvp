from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.connection import get_db
from app.api.dependencies.auth_dependencies import get_current_user
from app.models.db.user_model import User
import logging
from app.services.chat_service import save_user_message, save_gpt_response
from app.prompt.chat_prompt import build_chat_prompt
from app.models.schemas.chat_schema import MessageInput
from app.models.schemas.chat_schema import TurnInput, ChatResponseInput
from fastapi import HTTPException
from app.clients.gpt_api import stream_gpt_response
from fastapi.responses import StreamingResponse
from fastapi import Request
from app.services.session_create import get_or_create_session_id
import logging
from app.models.db.chat_message_model import ChatMessage
from datetime import datetime
from app.api.dependencies.auth_dependencies import get_current_user
from app.utils.time_utils import get_kst_now
from app.services.diary_service import DiaryService
import json
import redis
from app.config.settings import settings


router = APIRouter()
from app.api.dependencies.writing_dependencies import require_legacy_creation


# 채팅 메시지 저장
@router.post("/chat/send", dependencies=[Depends(require_legacy_creation)])
def send_message(
    data: MessageInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        # 20분 기준 반영된 세션 ID 조회/생성
        session_id = get_or_create_session_id(db, current_user.id)
        print(f"✅ [routers. /chat/send ] , session_id {session_id} ")

        # 메시지 저장 (session_id 포함)
        turn = save_user_message(
            db, current_user.id, data.message, session_id=session_id
        )
        print(f"turn : {turn} ")


        # turn과 session_id를 함께 반환
        return {
            "turn": turn,
            "session_id": session_id
        }
    except Exception as e:
        print("❌ /chat/send 에러:", type(e).__name__)
        raise HTTPException(status_code=500, detail="채팅 메시지 저장 실패")



# GPT 스트리밍 응답 생성 & 저장

logger = logging.getLogger(__name__)

@router.post("/chat/response_stream", dependencies=[Depends(require_legacy_creation)])
async def stream_response(
    data: ChatResponseInput,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        turn, session_id = data.turn, data.session_id
        # 요청한 turn이 실제 본인의 사용자 메시지인지 먼저 확인한다.
        source = db.query(ChatMessage).filter_by(
            user_id=current_user.id, session_id=session_id, turn=turn, role="user"
        ).first()
        if source is None:
            raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")

        # 프롬프트 구성
        prompt = build_chat_prompt(db, current_user.id, turn, session_id=session_id)

        # 구형 화면은 일반 텍스트를 표시한다. SSE는 지원을 명시한 클라이언트에만 보낸다.
        use_events = "text/event-stream" in request.headers.get("accept", "").lower()

        async def event_generator():
            accumulated = ""
            def frame(event, payload):
                if use_events:
                    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if event == "chunk":
                    return payload["text"]
                if event == "error":
                    return "\n[Error] " + payload["message"]
                return ""
            try:
                # 스트리밍 청크 전송
                async for chunk in stream_gpt_response(prompt):
                    accumulated += chunk
                    yield frame("chunk", {"text": chunk})

            except Exception as stream_err:
                logger.error("chat_stream_failed error_type=%s", type(stream_err).__name__)
                yield frame("error", {"code": "generation_failed", "message": "답변 생성에 실패했습니다. 잠시 후 다시 시도해 주세요."})
                return

            if not accumulated.strip():
                yield frame("error", {"code": "generation_failed", "message": "답변이 비어 있어 저장하지 않았습니다."})
                return

            # 스트리밍 완료 시 저장
            try:
                logger.info(
                    f"✅ Streaming complete (total_len={len(accumulated)}). Saving to DB."
                )
                save_gpt_response(
                    db, current_user.id, accumulated, turn, session_id=session_id
                )

            except Exception as save_err:
                logger.error("chat_save_failed error_type=%s", type(save_err).__name__)
                yield frame("error", {"code": "save_failed", "message": "답변은 생성됐지만 저장하지 못했습니다. 대화 기록을 다시 확인해 주세요."})
                return

            if use_events:
                yield frame("saved", {"turn": turn, "session_id": session_id})

            # 조건 체크 및 Redis 발행 (try 블록 밖으로)
            logger.info("🔍 save_gpt_response 완료, 조건 체크 시작")

            try:
                logger.info("🔍 DiaryService 생성 시작")
                diary_service = DiaryService()
                logger.info("✅ DiaryService 생성 완료")

                logger.info("🔍 조건 체크 함수 호출 시작")
                condition_result = await diary_service.check_diary_conditions(current_user.id)
                logger.info(f"🔍 조건 체크 결과: {condition_result}")

                if condition_result["available"]:
                    logger.info("🔍 available: true, Redis 발행 시작")
                    # Redis 발행 (websocket_service.py와 동일한 형태)
                    redis_client = redis.Redis(
                        host=settings.redis_host,
                        port=settings.redis_port,
                        db=settings.redis_db
                    )

                    message = {
                        "type": "diary_available",
                        "target": "blink-study-overlay-monitor",
                        "message": "일기 생성이 가능합니다!"
                    }

                    channel = f"user_{current_user.id}_diary"
                    message_json = json.dumps(message)

                    logger.info(f"🔍 Redis 발행 시도: channel={channel}, message={message_json}")
                    result = redis_client.publish(channel, message_json)
                else:
                    logger.info(f"🔍 available: false, Redis 발행 건너뜀")

            except Exception as check_err:
                logger.error("diary_condition_failed error_type=%s", type(check_err).__name__)

        return StreamingResponse(event_generator(), media_type="text/event-stream" if use_events else "text/plain", headers={"Cache-Control":"no-cache", "X-Accel-Buffering":"no", "Vary":"Accept"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error("chat_response_failed error_type=%s", type(e).__name__)
        raise HTTPException(status_code=500, detail="GPT 스트리밍 응답 처리 실패")

# /chat/history 라우터 :  채팅내용 렌더링하기
from pydantic import BaseModel
class DateRequest(BaseModel):
    date: str


@router.post("/chat/history")

def get_chat_history(req: DateRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)):
    """
    오늘 날짜 기준 채팅 기록 조회
    """

    # 문자열 날짜 → datetime.date 변환 (KST 기준)
    try:
        target_date = datetime.strptime(req.date, "%Y-%m-%d").date()
    except ValueError:
        return {"messages": []}

    # KST 기준으로 시작/끝 시간 설정
    from datetime import timezone, timedelta
    kst = timezone(timedelta(hours=9))
    start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=kst)
    end = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=kst)

    records = db.query(ChatMessage).filter(
        ChatMessage.user_id == user.id,
        ChatMessage.timestamp >= start,
        ChatMessage.timestamp <= end
    ).order_by(ChatMessage.timestamp.asc()).all()

    messages = [
      {
        "role": r.role,
        "message": r.message,
        "timestamp": r.timestamp.isoformat()
      }
      for r in records
    ]
    return {"messages": messages}


# 채팅 목록 조회 (날짜별 그룹화)
@router.get("/chat/list")
def get_chat_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        # 현재 유저의 모든 채팅 메시지 조회
        records = db.query(ChatMessage).filter(
            ChatMessage.user_id == current_user.id
        ).order_by(ChatMessage.timestamp.desc()).all()

        # timestamp에서 날짜 추출하여 그룹화
        chat_dates = set()
        for record in records:
            date_str = record.timestamp.strftime("%Y-%m-%d")
            chat_dates.add(date_str)

        # 날짜순으로 정렬 (최신순)
        sorted_dates = sorted(list(chat_dates), reverse=True)

        return {"chat_dates": sorted_dates}

    except Exception as e:
        print("❌ /chat/list 에러:", str(e))
        raise HTTPException(status_code=500, detail="채팅 목록 조회 실패")
