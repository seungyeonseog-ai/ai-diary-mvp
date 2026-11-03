"""추가 테이블만 생성하고 기존 체험 시작을 보존한다. 실행 시각으로 초기화하지 않는다."""
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
from app.models.db.access_model import AccountAccess, AccessChange
from app.models.db.user_model import User
from app.services.access_service import ensure_account


def migrate_access_schema(engine):
    if engine.dialect.name != "sqlite":
        raise RuntimeError("현재 이행 도구는 SQLite 전용입니다.")
    with engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        AccountAccess.__table__.create(connection, checkfirst=True)
        AccessChange.__table__.create(connection, checkfirst=True)
        with Session(bind=connection) as db:
            for user in db.scalars(select(User)):
                ensure_account(db, user)
            db.flush()


def require_access_schema(engine):
    if not {"account_access", "access_changes"} <= set(inspect(engine).get_table_names()):
        raise RuntimeError("이용권 스키마 이행 필요: tools/migrate_access.py를 백업과 함께 실행하세요.")
