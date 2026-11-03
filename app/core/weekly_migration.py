from sqlalchemy import text,inspect
from app.models.db.weekly_cycle_model import WeeklyActivation,WeeklyClock,AnalysisJob
from app.utils.time_utils import get_kst_now


def migrate_weekly_schema(engine,now=None):
    with engine.begin() as conn:
        if engine.dialect.name=='sqlite':conn.execute(text('BEGIN IMMEDIATE'))
        for cls in (WeeklyActivation,WeeklyClock,AnalysisJob):cls.__table__.create(conn,checkfirst=True)
        if not conn.execute(text('SELECT id FROM weekly_activation WHERE id=1')).first():
            conn.execute(WeeklyActivation.__table__.insert().values(id=1,activated_at=now or get_kst_now()))


def require_weekly_schema(engine):
    if not {'weekly_activation','weekly_clocks','analysis_jobs'}<=set(inspect(engine).get_table_names()):raise RuntimeError('백업 후 tools.migrate_weekly 이행이 필요합니다.')
