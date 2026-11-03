import argparse,sqlite3
from pathlib import Path
from datetime import datetime
from contextlib import closing
from sqlalchemy import create_engine
from tools.migrate_writing import original_digest
from app.core.weekly_migration import migrate_weekly_schema


def migrate(path):
    path=Path(path).resolve(strict=True);backup=path.with_name('weekly-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.db')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(backup)) as target:
        source.backup(target);before=original_digest(target)
    engine=create_engine('sqlite:///'+path.as_posix())
    try:migrate_weekly_schema(engine)
    finally:engine.dispose()
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        assert original_digest(db)==before and db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    print('PASS weekly migration; original digest unchanged; backup='+str(backup))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--database',required=True);migrate(p.parse_args().database)
