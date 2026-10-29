from app.utils.time_utils import get_kst_now
import json
from sqlalchemy.orm import Session
from app.repositories.today_chat_message_repository import TodayChatMessageRepository
from app.models.db.study_model import EncouragementReport
from app.models.db.user_model import User
from app.clients.gpt_api import call_gpt
from datetime import datetime
import redis
from app.config.settings import settings
from app.prompt.encourage_diary_prompt import encourage_diary_prompt, encourage_letter_prompt




class EncourageDiaryService:
    def __init__(self, db: Session):
        self.db = db
        self.today_chat_repo = TodayChatMessageRepository()
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db
        )

    def create_encouragement(self, user_id: int):
        """사용자 격려 메시지 생성"""

        try:
            # 1. user의 nickname 가져오기
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                print(f"❌ [ERROR] user_id={user_id}인 사용자를 찾을 수 없습니다.")
                return False

            nickname = user.nickname


            # 2. user 채팅 내용 가져오기
            combined_content, total_tokens = self.today_chat_repo.get_today_user_chat_content_and_tokens(user_id)

            # 3. GPT API 호출 (시스템 메시지 + 사용자 메시지)
            music_enabled = settings.music_recommendations_enabled
            prompt_template = encourage_diary_prompt if music_enabled else encourage_letter_prompt
            system_message = (
                "오늘의 응원 메시지와 어울리는 노래를 추천해주세요. 정확한 JSON으로 응답해주세요."
                if music_enabled else "오늘 하루를 마무리하는 응원 편지를 작성해주세요. 정확한 JSON으로 응답해주세요."
            )
            prompt = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt_template.format(content=combined_content, nickname=nickname)}
            ]

            # 3. GPT 호출
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
            except json.JSONDecodeError as e:
                print(f"❌ [ERROR] JSON 파싱 실패: {type(e).__name__}")
                raise Exception(f"GPT 응답이 유효한 JSON이 아닙니다: {e}")

            if not isinstance(result, dict) or not isinstance(result.get("encourage_content"), str) or not result["encourage_content"].strip():
                return False

            # 4. DB 저장
            try:
                encouragement = EncouragementReport(
                    user_id=user_id,
                    encourage_content=result["encourage_content"],
                    music=result.get("music", []) if music_enabled else [],
                    singer=result.get("singer", []) if music_enabled else [],
                    timestamp=get_kst_now()
                )
                self.db.add(encouragement)
                self.db.commit()
                print(f"💾 [DEBUG] DB 저장 성공: user_id={user_id}")
            except Exception as e:
                print(f"❌ [ERROR] DB 저장 실패: {type(e).__name__}")
                self.db.rollback()
                raise Exception(f"DB 저장 중 오류 발생: {e}")

            # 5. Redis 발행
            try:
                message = {
                    "type": "encourage_availalbe",
                    "target": "letter",
                    "message": "오늘 하루도 수고했어요, 당신에게 편지가 왔어요",
                    "date": encouragement.timestamp.date().isoformat(),
                    "result_id": encouragement.encouragement_id
                }

                channel = f"user_{user_id}_encourage"
                message_json = json.dumps(message)

                print(f"📤 [DEBUG] Redis 발행 시도: channel={channel}, message={message_json}")
                result = self.redis_client.publish(channel, message_json)

            except Exception as e:
                print(f"❌ [ERROR] Redis 발행 실패: {type(e).__name__}")
                # Redis 발행 실패는 치명적이지 않으므로 예외를 다시 발생시키지 않음

            return encouragement

        except Exception as e:
            print(f"❌ [ERROR] 격려 메시지 생성 실패: user_id={user_id}, error_type={type(e).__name__}")
            return False
