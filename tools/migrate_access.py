"""온라인 백업 후 이용권 테이블을 추가한다. 기존 테이블 내용을 출력하지 않는다."""
import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine
from app.core.access_migration import migrate_access_schema


def digest_existing(connection):
    digest = hashlib.sha256()
    names = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
             if r[0] not in ("account_access", "access_changes", "sqlite_sequence")]
    for name in names:
        quoted = '"' + name.replace('"', '""') + '"'
        rows = [json.dumps(list(row), ensure_ascii=False, default=lambda v: {"bytes": bytes(v).hex()})
                for row in connection.execute(f"SELECT * FROM {quoted}")]
        digest.update(json.dumps([name, sorted(rows)], ensure_ascii=False).encode("utf-8"))
    return digest.hexdigest()


def migrate(path):
    path = Path(path).resolve(strict=True)
    backup = path.with_name("access-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".db")
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)) as source, closing(sqlite3.connect(backup)) as target:
        source.backup(target)
    engine = create_engine("sqlite:///" + path.as_posix(), hide_parameters=True)
    try:
        migrate_access_schema(engine)
    finally:
        engine.dispose()
    print(json.dumps({"backup": str(backup), "migration": "complete"}, ensure_ascii=False))
    return backup


def verify_copy(path):
    """운영 파일은 읽기 전용으로 열고 복사본에서 전체 기존 테이블을 비교한다."""
    path = Path(path).resolve(strict=True)
    copy = path.with_name("access-check-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")+".db")
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)) as source, closing(sqlite3.connect(copy)) as target:
        source.backup(target)
        before = digest_existing(target)
    migrate(copy)
    engine = create_engine("sqlite:///"+copy.as_posix(), hide_parameters=True)
    try:
        migrate_access_schema(engine)
    finally:
        engine.dispose()
    with closing(sqlite3.connect(copy)) as db:
        assert digest_existing(db) == before, "Existing table preservation failed"
        count = db.execute("SELECT COUNT(*) FROM account_access").fetchone()[0]
        assert count == db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(json.dumps({"copy": str(copy), "existing_tables_preserved": True,
                      "repeat_safe": True, "accounts": count}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--verify-copy", action="store_true")
    args = parser.parse_args()
    (verify_copy if args.verify_copy else migrate)(args.database)
