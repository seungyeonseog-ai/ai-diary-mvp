"""실행: python -m tools.migrate_daily --database .local-check/test.db"""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine
from app.models.db.user_model import User
from app.models.db.chat_message_model import ChatMessage
from app.models.db.session_log import SessionLog
from app.models.db.session_summary import GPTSessionSummary
from app.models.db.writing_model import Writing
from app.core.daily_migration import migrate_daily_schema
from tools.migrate_writing import original_digest


def migrate(path):
    path=Path(path).resolve(strict=True)
    backup=path.with_name('daily-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.db')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as source, closing(sqlite3.connect(backup)) as target:
        source.backup(target)
        before=original_digest(target)
    engine=create_engine('sqlite:///'+path.as_posix(),hide_parameters=True)
    try:
        migrate_daily_schema(engine)
    finally:
        engine.dispose()
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as conn:
        if original_digest(conn)!=before or conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('원본 보존/무결성 확인 실패. 백업을 보존하고 조사하세요.')
    print('Daily migration complete; backup='+str(backup))
    print('PASS: original diary/chat/account digest unchanged; integrity_check=ok')
    return backup


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--database',required=True)
    migrate(parser.parse_args().database)
