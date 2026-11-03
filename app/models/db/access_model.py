"""체험 기간과 이용권을 분리한다. 결제 정보나 사용자 원문을 보관하지 않는다."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from app.core.connection import Base


class AccountAccess(Base):
    __tablename__ = "account_access"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    trial_started_at = Column(DateTime)
    trial_expires_at = Column(DateTime)
    plan = Column(String(30), nullable=False, default="free")
    pass_started_at = Column(DateTime)
    pass_expires_at = Column(DateTime)
    cancelled_at = Column(DateTime)


class AccessChange(Base):
    __tablename__ = "access_changes"
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    request_id = Column(String(80), nullable=False)
    action = Column(String(20), nullable=False)
    old_plan = Column(String(30), nullable=False)
    new_plan = Column(String(30), nullable=False)
    effective_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime)
    __table_args__ = (UniqueConstraint("user_id", "request_id"),)
