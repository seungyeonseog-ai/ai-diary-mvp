"""날짜별 논리 작업과 편지 상태. 원문은 chat_messages에만 보관한다."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, ForeignKey, UniqueConstraint
from app.core.connection import Base


class DailySettings(Base):
    __tablename__ = 'daily_settings'
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    hour = Column(Integer, nullable=False, default=22)
    previous_hour = Column(Integer, nullable=False, default=22)
    effective_date = Column(String(10), nullable=False)
    configured = Column(Boolean, nullable=False, default=False)


class DailyJob(Base):
    __tablename__ = 'daily_jobs'
    id = Column(String(80), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    source_date = Column(String(10), nullable=False)
    phase = Column(String(20), nullable=False)
    cutoff = Column(DateTime, nullable=False)
    source_ids = Column(JSON, nullable=False)
    summary_result = Column(JSON)
    summary_indexed = Column(Boolean, nullable=False, default=False)
    letter_result = Column(JSON)
    letter_done = Column(Boolean, nullable=False, default=False)
    state = Column(String(20), nullable=False, default='pending')
    lease_token = Column(String(36))
    lease_until = Column(DateTime)
    retry_at = Column(DateTime)
    attempts = Column(Integer, nullable=False, default=0)
    error_type = Column(String(100))
    __table_args__ = (UniqueConstraint('user_id', 'source_date', 'phase'),)


class LetterDelivery(Base):
    __tablename__ = 'letter_deliveries'
    id = Column(Integer, ForeignKey('encouragement_reports.encouragement_id'), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    source_date = Column(String(10), nullable=False)
    saved = Column(Boolean, nullable=False, default=False)
    discarded = Column(Boolean, nullable=False, default=False)
    viewed_at = Column(DateTime)
    archive_deleted = Column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint('user_id', 'source_date'),)


class ResultNotice(Base):
    __tablename__ = 'result_notices'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    kind = Column(String(20), nullable=False)
    result_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)
    badge_seen_at = Column(DateTime)
    published_at = Column(DateTime)
    __table_args__ = (UniqueConstraint('user_id', 'kind', 'result_id'),)


class DailyActivation(Base):
    __tablename__ = 'daily_activation'
    id = Column(Integer, primary_key=True)
    activated_at = Column(DateTime, nullable=False)
