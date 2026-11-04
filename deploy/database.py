"""새 DB 초기화와 명시적 기존 DB 이행. 원문은 출력하지 않는다."""
import argparse
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import pkgutil
import sqlite3
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url


def load_models():
    from app.models import db
    for module in pkgutil.iter_modules(db.__path__):
        importlib.import_module("app.models.db." + module.name)
    from app.core.connection import Base
    return Base


def verify(engine):
    from app.core.access_migration import require_access_schema
    from app.core.writing_migration import require_writing_schema
    from app.core.daily_migration import require_daily_schema
    from app.core.weekly_migration import require_weekly_schema
    for check in (require_access_schema, require_writing_schema, require_daily_schema, require_weekly_schema):
        check(engine)
    with engine.connect() as conn:
        if conn.exec_driver_sql("PRAGMA quick_check").scalar() != "ok":
            raise RuntimeError("SQLite integrity check failed")
        if "published_at" not in {c["name"] for c in inspect(conn).get_columns("result_notices")}:
            raise RuntimeError("Daily notification migration required")


def path_for(url):
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or parsed.database in (None, "", ":memory:"):
        raise ValueError("A persistent SQLite file is required")
    return Path(parsed.database).resolve()


def backup(path):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = path.with_name(path.name + ".pre-migration-" + stamp + ".db")
    source = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    dest = sqlite3.connect(target)
    try:
        source.backup(dest)
        if dest.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup integrity check failed")
    finally:
        dest.close()
        source.close()
    return target


def prepare(url, *, migrate=False):
    path = path_for(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, hide_parameters=True)
    saved = None
    try:
        Base = load_models()
        tables = set(inspect(engine).get_table_names())
        if tables:
            # init은 기존 자료를 자동 이행하거나 빈 DB로 대체하지 않는다.
            if not migrate:
                verify(engine)
                return {"action": "verified-existing", "backup_created": False}
            if not {"users", "diary_reports"} <= tables:
                raise RuntimeError("Unrecognized database; refusing migration")
            saved = backup(path)
        Base.metadata.create_all(engine)
        from app.core.writing_migration import migrate_writing_schema
        from app.core.access_migration import migrate_access_schema
        from app.core.daily_migration import migrate_daily_schema
        from app.core.weekly_migration import migrate_weekly_schema
        for migration in (migrate_writing_schema, migrate_access_schema, migrate_daily_schema, migrate_weekly_schema):
            migration(engine)
        verify(engine)
        return {"action": "migrated" if tables else "initialized-new", "backup_created": saved is not None}
    finally:
        engine.dispose()


if __name__ == "__main__":
    from deploy.preflight import validate
    validate()
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "migrate"])
    parser.add_argument("--database-url")
    args = parser.parse_args()
    from app.config.settings import settings
    print(json.dumps(prepare(args.database_url or settings.database_url, migrate=args.action == "migrate")))
