"""체험 기간과 상품 선택 의향. 결제 정보나 사용자 원문을 보관하지 않는다."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from app.core.connection import Base


class AccountAccess(Base):
    __tablename__ = "account_access"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    trial_started_at = Column(DateTime)
    trial_expires_at = Column(DateTime)
    # 첫 이행의 NOT NULL 컬럼과 호환하기 위한 고정값. 권한 판정에는 사용하지 않는다.
    plan = Column(String(30), nullable=False, default="free")


class AccountPlanChoice(Base):
    """결제·권한 부여와 분리된 베타 상품 선택 의향 이력."""
    __tablename__ = "account_plan_choices"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    request_id = Column(String(80), nullable=False)
    plan = Column(String(30), nullable=False)
    chosen_at = Column(DateTime, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "request_id"),)
