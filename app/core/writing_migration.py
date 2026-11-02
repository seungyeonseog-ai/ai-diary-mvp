"""필드 추가형 SQLite 이행. 기존 원문/ID/시간은 바꾸지 않는다.

기존 파일 이행은 tools/migrate_writing.py로 백업 뒤 실행한다.
앱 시작은 이미 이행된 스키마인지 검사만 한다.
"""
from sqlalchemy import inspect, text
from app.models.db import writing_model  # noqa: F401
from app.models.db.study_model import DiaryReport
from app.utils.time_utils import get_kst_now

ADDITIONS = {
    "title": "TEXT NOT NULL DEFAULT ''",
    "state": "VARCHAR(20) NOT NULL DEFAULT 'saved'",
    "version": "INTEGER NOT NULL DEFAULT 1",
    "updated_at": "DATETIME",
}


def migrate_writing_schema(engine):
    if engine.dialect.name != "sqlite":
        raise RuntimeError("이 이행 도구는 현재 SQLite 구성 전용입니다.")
    with engine.begin() as connection:
        connection.execute(text("BEGIN IMMEDIATE"))
        columns = {c["name"] for c in inspect(connection).get_columns("diary_reports")}
        for name, ddl in ADDITIONS.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE diary_reports ADD COLUMN {name} {ddl}"))
        user_columns = {c["name"] for c in inspect(connection).get_columns("users")}
        if "registered_at" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN registered_at DATETIME"))
        if "trial_started_at" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN trial_started_at DATETIME"))
        # 기존 가입일을 조작하지 않는다. 재실행해도 체험 시각을 초기화하지 않는다.
        connection.execute(text("UPDATE users SET trial_started_at=:now "
                                "WHERE registered_at IS NULL AND trial_started_at IS NULL"),
                           {"now": get_kst_now()})
        for table in (writing_model.Writing.__table__, writing_model.WritingMessage.__table__,
                      writing_model.WritingOperation.__table__, writing_model.SummaryRange.__table__,
                      writing_model.DiaryPhoto.__table__):
            table.create(connection, checkfirst=True)


def require_writing_schema(engine):
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("diary_reports")}
    user_columns = {c["name"] for c in inspector.get_columns("users")}
    if set(ADDITIONS) - columns or not {"registered_at", "trial_started_at"} <= user_columns:
        raise RuntimeError("작성 스키마 이행 필요: tools/migrate_writing.py를 백업과 함께 실행하세요.")
