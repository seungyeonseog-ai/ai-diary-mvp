"""체험 기간과 무료 전환 기반. 결제 정보나 사용자 원문을 보관하지 않는다."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from app.core.connection import Base


class AccountAccess(Base):
    __tablename__ = "account_access"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    trial_started_at = Column(DateTime)
    trial_expires_at = Column(DateTime)
    # 첫 이행의 NOT NULL 컬럼과 호환하기 위한 고정값. 권한 판정에는 사용하지 않는다.
    plan = Column(String(30), nullable=False, default="free")
