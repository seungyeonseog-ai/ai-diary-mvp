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
from app.prompt.encourage_diary_prompt import encourage_diary_prompt




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
            print(f"🔍 [DEBUG] user_id={user_id}, nickname={nickname}")
            
            # 2. user 채팅 내용 가져오기
            combined_content, total_tokens = self.today_chat_repo.get_today_user_chat_content_and_tokens(user_id)
            
            # 3. GPT API 호출 (시스템 메시지 + 사용자 메시지)
            prompt = [
                {"role": "system", "content": "당신은 오늘 하루를 마무리 하는 사람에게 응원의 메시지와 그날의 어울리는 노래를 추천해주는 역할입니다.프롬프트 형식을 따라주세요. 정확한 JSON 형태로 응답해주세요."},
                {"role": "user", "content": encourage_diary_prompt.format(content=combined_content, nickname=nickname)}
            ]

            print(f"닉네임 : {nickname}")


            print(f"🔍 [DEBUG] prompt 전송: user_id={user_id}")
            
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
                print(f"❌ [ERROR] JSON 파싱 실패: {e}")
                raise Exception(f"GPT 응답이 유효한 JSON이 아닙니다: {e}")
            
            # 4. DB 저장
            try:
                encouragement = EncouragementReport(
                    user_id=user_id,
                    encourage_content=result["encourage_content"],
                    music=result["music"],
                    singer=result["singer"],
                    timestamp=get_kst_now()
                )
                self.db.add(encouragement)
                self.db.commit()
                print(f"💾 [DEBUG] DB 저장 성공: user_id={user_id}")
            except Exception as e:
                print(f"❌ [ERROR] DB 저장 실패: {e}")
                self.db.rollback()
                raise Exception(f"DB 저장 중 오류 발생: {e}")
            
            # 5. Redis 발행
            try:
                message = {
                    "type": "encourage_availalbe",
                    "target": "letter",
                    "message": "오늘 하루도 수고했어요, 당신에게 편지가 왔어요"
                }
                
                channel = f"user_{user_id}_encourage"
                message_json = json.dumps(message)
                
                print(f"📤 [DEBUG] Redis 발행 시도: channel={channel}, message={message_json}")
                result = self.redis_client.publish(channel, message_json)
                
            except Exception as e:
                print(f"❌ [ERROR] Redis 발행 실패: {e}")
                # Redis 발행 실패는 치명적이지 않으므로 예외를 다시 발생시키지 않음
            
            return encouragement
            
        except Exception as e:
            print(f"❌ [ERROR] 격려 메시지 생성 실패: user_id={user_id}, error={e}")
            return False



