"""직접 일기의 본인/한국 날짜별 중복 확인과 저장을 한 트랜잭션으로 처리한다."""
from datetime import datetime, timedelta
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.models.db.study_model import DiaryReport
from app.models.db.user_model import User
from app.utils.time_utils import get_kst_now

class ManualDiaryAlreadyExists(Exception):
    pass

def save_manual_diary(bind, user_id: int, content: str):
    # 인증 조회 세션과 분리하여 읽기/검사 사이 경쟁을 막는다.
    with Session(bind=bind, expire_on_commit=False) as db:
        try:
            if bind.dialect.name == "sqlite":
                # SQLite는 행 잠금이 없어 짧은 쓰기 트랜잭션을 먼저 예약한다.
                db.execute(text("BEGIN IMMEDIATE"))
            else:
                db.execute(select(User.id).where(User.id == user_id).with_for_update()).scalar_one()
            now = get_kst_now()
            start = datetime.combine(now.date(), datetime.min.time())
            existing = db.query(DiaryReport.diary_id).filter(
                DiaryReport.user_id == user_id,
                DiaryReport.source_type == "user",
                DiaryReport.state != "discarded",
                DiaryReport.timestamp >= start,
                DiaryReport.timestamp < start + timedelta(days=1),
            ).first()
            if existing:
                raise ManualDiaryAlreadyExists()
            row = DiaryReport(user_id=user_id, content=content, source_type="user", timestamp=now)
            db.add(row)
            db.commit()
            return row
        except Exception:
            db.rollback()
            raise
