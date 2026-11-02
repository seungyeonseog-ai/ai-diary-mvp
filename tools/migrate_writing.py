"""SQLite 온라인 백업 후 작성 스키마만 이행. 원문은 출력하지 않는다.

python -m tools.migrate_writing --database .local-check/test.db
"""
import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine
from app.models.db.user_model import User  # noqa: F401
from app.models.db.session_log import SessionLog  # noqa: F401
from app.models.db.chat_message_model import ChatMessage  # noqa: F401
from app.core.writing_migration import migrate_writing_schema


def original_digest(connection):
    digest = hashlib.sha256()
    for table, fields, order in (
        ("diary_reports", "diary_id,user_id,content,source_type,timestamp", "diary_id"),
        ("chat_messages", "id,user_id,session_id,role,message,timestamp,turn", "id"),
        ("users", "id,username,email,hashed_password,nickname", "id"),
    ):
        for row in connection.execute(f"SELECT {fields} FROM {table} ORDER BY {order}"):
            digest.update(json.dumps([table, list(row)], ensure_ascii=False).encode("utf-8"))
    return digest.hexdigest()


def migrate(path):
    path = Path(path).resolve(strict=True)
    backup = path.parent / ("writing-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".db")
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)) as source, closing(sqlite3.connect(backup)) as target:
        source.backup(target)
    # 백업을 복사한 뒤 실제 이행을 수행. 이행 동안 기존 원본 쓰기가 있으면 보존검사는
    # 복사본 검사와 달리 달라질 수 있으므로 운영 중 복구는 서비스 정지 후 한다.
    engine = create_engine("sqlite:///" + path.as_posix(), hide_parameters=True)
    migrate_writing_schema(engine)
    engine.dispose()
    print(json.dumps({"backup": str(backup), "migration": "complete"}, ensure_ascii=False))
    return backup


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    migrate(args.database)
