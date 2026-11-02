# models/user_model.py

from sqlalchemy import Column, Integer, String, DateTime
from app.utils.time_utils import get_kst_now
from app.core.connection import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)                    # 내부용 자동 증가 고유 ID
    username = Column(String, unique=True, nullable=False)               # 사용자가 입력하는 고유 아이디
    email = Column(String, unique=True, index=True, nullable=False)      # 이메일 (중복 방지)
    hashed_password = Column(String, nullable=False)                     # 암호화된 비밀번호
    nickname = Column(String, nullable=False)                            # 유저 닉네임
    registered_at = Column(DateTime, nullable=True, default=get_kst_now)
    # 가입 시각이 없는 기존 계정의 체험 시작일은 별도 보관한다.
    trial_started_at = Column(DateTime, nullable=True)



print("✅ User 클래스 정의됨:", User)
