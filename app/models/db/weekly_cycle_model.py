"""일일 감정 분석과 고정 7일 주간 작업의 원본·성공 체크포인트."""
from sqlalchemy import Column,Integer,String,DateTime,JSON,ForeignKey,UniqueConstraint
from app.core.connection import Base


class WeeklyActivation(Base):
    __tablename__='weekly_activation'
    id=Column(Integer,primary_key=True)
    activated_at=Column(DateTime,nullable=False)


class WeeklyClock(Base):
    __tablename__='weekly_clocks'
    user_id=Column(Integer,ForeignKey('users.id'),primary_key=True)
    anchor_date=Column(String(10),nullable=False)


class AnalysisJob(Base):
    __tablename__='analysis_jobs'
    id=Column(String(90),primary_key=True)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    kind=Column(String(20),nullable=False)
    start_date=Column(String(10),nullable=False)
    end_date=Column(String(10),nullable=False)
    source_ids=Column(JSON,nullable=False)
    result=Column(JSON)
    result_id=Column(Integer)
    state=Column(String(20),nullable=False,default='pending')
    lease_token=Column(String(36))
    lease_until=Column(DateTime)
    retry_at=Column(DateTime)
    attempts=Column(Integer,nullable=False,default=0)
    error_type=Column(String(100))
    __table_args__=(UniqueConstraint('user_id','kind','end_date'),)
