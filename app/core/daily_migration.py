"""기존 중복 자료는 그대로 두고 신규 중복만 차단한다."""
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session
from app.models.db import daily_model as models
from app.models.db.study_model import EncouragementReport
from app.utils.time_utils import get_kst_now


def migrate_daily_schema(engine, now=None):
    now=now or get_kst_now()
    if engine.dialect.name!='sqlite':
        raise RuntimeError('현재 이행은 SQLite 전용입니다.')
    with engine.begin() as conn:
        conn.execute(text('BEGIN IMMEDIATE'))
        for cls in (models.DailySettings,models.DailyJob,models.LetterDelivery,models.ResultNotice,models.DailyActivation):
            cls.__table__.create(conn,checkfirst=True)
        if 'published_at' not in {c['name'] for c in inspect(conn).get_columns('result_notices')}:
            conn.execute(text('ALTER TABLE result_notices ADD COLUMN published_at DATETIME'))
        # 기존 중복 행을 삭제/병합하지 않는다. 신규 INSERT와 상태 복원만 차단.
        conn.execute(text("""CREATE TRIGGER IF NOT EXISTS diary_day_insert BEFORE INSERT ON diary_reports
            WHEN NEW.state != 'discarded' AND EXISTS(SELECT 1 FROM diary_reports
            WHERE user_id=NEW.user_id AND date(timestamp)=date(NEW.timestamp) AND state!='discarded')
            BEGIN SELECT RAISE(ABORT,'daily_diary_exists'); END"""))
        conn.execute(text("""CREATE TRIGGER IF NOT EXISTS diary_day_restore BEFORE UPDATE OF state,user_id,timestamp ON diary_reports
            WHEN NEW.state!='discarded' AND (OLD.state!=NEW.state OR NEW.user_id!=OLD.user_id OR date(NEW.timestamp)!=date(OLD.timestamp))
            AND EXISTS(SELECT 1 FROM diary_reports WHERE diary_id!=NEW.diary_id AND user_id=NEW.user_id
            AND date(timestamp)=date(NEW.timestamp) AND state!='discarded')
            BEGIN SELECT RAISE(ABORT,'daily_diary_exists'); END"""))
        conn.execute(text("""CREATE TRIGGER IF NOT EXISTS letter_day_insert BEFORE INSERT ON encouragement_reports
            WHEN EXISTS(SELECT 1 FROM encouragement_reports WHERE user_id=NEW.user_id AND date(timestamp)=date(NEW.timestamp))
            BEGIN SELECT RAISE(ABORT,'daily_letter_exists'); END"""))
    with Session(engine) as db:
        if not db.get(models.DailyActivation,1):
            db.add(models.DailyActivation(id=1,activated_at=now))
        # 기존 응원도 날짜별 최근 1개를 연결. 원래 결과는 수정/삭제하지 않는다.
        rows=db.query(EncouragementReport).order_by(EncouragementReport.timestamp.desc(),EncouragementReport.encouragement_id.desc()).all()
        seen={(r.user_id,r.source_date) for r in db.query(models.LetterDelivery)}
        for row in rows:
            key=(row.user_id,row.timestamp.date().isoformat())
            if key not in seen:
                db.add(models.LetterDelivery(id=row.encouragement_id,user_id=key[0],source_date=key[1],
                    saved=False,discarded=False,archive_deleted=False))
                seen.add(key)
        db.commit()


def require_daily_schema(engine):
    names=set(inspect(engine).get_table_names())
    if not {'daily_activation','daily_jobs','daily_settings','letter_deliveries','result_notices'}<=names:
        raise RuntimeError('백업 후 tools.migrate_daily 이행이 필요합니다.')
    with engine.connect() as conn:
        if not conn.execute(text('SELECT id FROM daily_activation WHERE id=1')).first():
            raise RuntimeError('날짜별 작업 활성화 이행이 필요합니다. tools.migrate_daily를 실행하세요.')
