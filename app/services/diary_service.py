from sqlalchemy.orm import Session
from datetime import datetime, date
from app.prompt.diary_prompt import DiaryPromptService

from app.models.db.study_model import DiaryReport
from app.repositories.today_chat_message_repository import TodayChatMessageRepository
from app.models.schemas.study_schema import DiaryResponse
from app.clients.gpt_api import GPTClient
from app.core.connection import get_db
from app.config.settings import settings
import json
import redis
import logging
from app.core.operation_lock import diary_generation_lock
from app.utils.time_utils import get_kst_now

logger = logging.getLogger(__name__)


def stream_event(event, payload):
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


class DiaryService:
    def __init__(self):
        self.prompt_service = DiaryPromptService()
        self.chat_repository = TodayChatMessageRepository()
        self.gpt_client = GPTClient()
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db
        )

    async def check_diary_conditions(self, user_id: int):
        """일기 생성 조건 체크 - 라우터와 동일한 로직"""
        try:
            # 오늘 AI 생성 여부 확인 (source_type='ai')
            today_ai_diary = self.chat_repository.check_today_diary_by_source(user_id, 'ai')
            if today_ai_diary:
                return {
                    "available": False
                }
            
            # 오늘 사용자 채팅 토큰수 확인
            formatted_chats, total_tokens = self.chat_repository.diary_get_today_user_chat_and_tokens(user_id)
            min_tokens = 55  # 최소 토큰수 설정
            if total_tokens < min_tokens:
                return {
                    "available": False
                }
            
            return {
                "available": True
            }
            
        except Exception as e:
            return {
                "available": False
            }
        



    async def generate_diary_stream(self, user_id: int):
        """생성 청크와 DB 저장 완료/실패를 구분해 전송한다."""
        db = None
        try:
            async with diary_generation_lock(user_id) as renewal:
                if self.chat_repository.check_today_diary_by_source(user_id, 'ai'):
                    yield stream_event("error", {"message": "오늘 이미 AI로 생성한 일기가 있습니다."})
                    return
                started_at = get_kst_now()
                formatted_chats, _ = self.chat_repository.diary_get_today_user_chat_and_tokens(user_id)
                prompt = self.prompt_service.generate_diary_prompt(formatted_chats)
                full_content = ""
                async for chunk in self.gpt_client.stream_gpt_response(prompt):
                    if renewal.done():
                        renewal.result()
                    full_content += chunk
                    yield stream_event("chunk", {"text": chunk})
                if not full_content.strip():
                    raise ValueError("Empty diary")
                if renewal.done():
                    renewal.result()
                db = next(get_db())
                diary_report = DiaryReport(
                    user_id=user_id, content=full_content,
                    source_type='ai', timestamp=started_at,
                )
                db.add(diary_report)
                db.commit()
                diary_id = diary_report.diary_id
                # 저장 성공 이후의 잠금 해제·알림 실패는 성공 상태를 뒤집지 않는다.
                yield stream_event("saved", {"diary_id": diary_id})
                try:
                    self.redis_client.publish(f"user_{user_id}_diary", json.dumps({
                        "type": "diary_unavailable", "priority": "high",
                        "reason": "ai_diary_created",
                    }))
                except Exception:
                    logger.warning("Diary notification failed", exc_info=False)
        except Exception:
            if db is not None:
                db.rollback()
            logger.error("Diary generation or persistence failed", exc_info=False)
            yield stream_event("error", {"message": "일기를 생성하거나 저장하지 못했습니다. 목록을 확인한 뒤 다시 시도해 주세요."})
        finally:
            if db is not None:
                db.close()

    async def save_diary(self, user_id: int, content: str, source_type: str = 'ai'):
        """일기 저장"""
        db = next(get_db())
        try:
            diary_report = DiaryReport(
                user_id=user_id,
                content=content,
                source_type=source_type,
                timestamp=get_kst_now()  # 시스템 로컬 시간 사용 (KST)
            )
            db.add(diary_report)
            db.commit()
            return diary_report
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
