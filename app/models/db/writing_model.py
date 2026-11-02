"""작성 시도는 기술 채팅 세션과 별개다. 원본 대화는 폐기해도 보존한다."""
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, UniqueConstraint, LargeBinary
from sqlalchemy.orm import deferred
from app.core.connection import Base


class Writing(Base):
    __tablename__ = "writings"
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source_date = Column(String(10), nullable=False)
    state = Column(String(20), nullable=False, default="active")
    diary_id = Column(Integer, ForeignKey("diary_reports.diary_id"), unique=True)
    created_at = Column(DateTime, nullable=False)
    closed_at = Column(DateTime)


class WritingMessage(Base):
    __tablename__ = "writing_messages"
    message_id = Column(Integer, ForeignKey("chat_messages.id"), primary_key=True)
    writing_id = Column(String(36), ForeignKey("writings.id"), nullable=False, index=True)
    client_id = Column(String(80), nullable=False)
    __table_args__ = (UniqueConstraint("writing_id", "client_id"),)


class WritingOperation(Base):
    __tablename__ = "writing_operations"
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    writing_id = Column(String(36), ForeignKey("writings.id"), nullable=False)
    client_id = Column(String(80), nullable=False)
    kind = Column(String(20), nullable=False)
    source_ids = Column(JSON, nullable=False)
    source_date = Column(String(10), nullable=False)
    quota_kind = Column(String(20))
    state = Column(String(20), nullable=False)
    lease_token = Column(String(36))
    lease_until = Column(DateTime)
    result = Column(JSON)
    created_at = Column(DateTime, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "client_id"),)


class SummaryRange(Base):
    """6번 예약 처리에 연결할 성공 원본 구간. 폐기 상태로 필터하지 않는다."""
    __tablename__ = "summary_ranges"
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source_date = Column(String(10), nullable=False)
    phase = Column(String(20), nullable=False)  # encouragement / midnight
    source_ids = Column(JSON, nullable=False)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "source_date", "phase"),)


class DiaryPhoto(Base):
    __tablename__ = "diary_photos"
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    diary_id = Column(Integer, ForeignKey("diary_reports.diary_id"), nullable=False, index=True)
    client_id = Column(String(80), nullable=False)
    media_type = Column(String(30), nullable=False)
    digest = Column(String(64), nullable=False)
    # 정적 공개 경로를 만들지 않고 인증된 API로만 반환한다.
    content = deferred(Column(LargeBinary, nullable=False))
    created_at = Column(DateTime, nullable=False)
    __table_args__ = (UniqueConstraint("diary_id", "client_id"),)
