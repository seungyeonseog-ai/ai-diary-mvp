"""실제 제품UI·API, 합성 DB/고정 시각. 유료 API 경로는 비활성."""
from tests.browser.library_server import app,engine
from datetime import datetime,timedelta
from sqlalchemy.orm import Session
from app.models.db.daily_model import DailySettings,LetterDelivery,ResultNotice,DailyJob
from app.models.db.study_model import EncouragementReport
from app.core.daily_migration import migrate_daily_schema
from app.api.routers import daily_router,study_router
from app.services import daily_service,study_state_service
from app.utils.time_utils import get_kst_now
import os,sqlite3
from pathlib import Path

letter_body='서재검증1님, 오늘 작은 일을 끝낸 마음을 기억해요.\n잠시 쉬어가도 괜찮아요.\n내일도 당신의 속도로 걸어가요.'
if os.environ.get('DAILY_AI_TEST_DB'):
    source=Path(os.environ['DAILY_AI_TEST_DB']).resolve(strict=True)
    if not source.parent.name.startswith('daily-ai-'):raise ValueError('격리 AI 검증 DB만 허용')
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as read:
        letter_body=read.execute('SELECT encourage_content FROM encouragement_reports LIMIT 1').fetchone()[0]

clock={'now':get_kst_now().replace(hour=22,minute=5,second=0,microsecond=0)}
for module in (daily_router,daily_service,study_state_service):module.get_kst_now=lambda:clock['now']
migrate_daily_schema(engine,clock['now'])
app.include_router(daily_router.router)
app.router.routes=[r for r in app.router.routes if getattr(r,'path','')!='/study/status']
app.include_router(study_router.router)
with Session(engine) as db:
    for offset in (0,1):
        when=clock['now']-timedelta(days=offset)
        report=EncouragementReport(user_id=1,encourage_content=letter_body,music=[],singer=[],timestamp=when)
        db.add(report);db.flush()
        db.add(LetterDelivery(id=report.encouragement_id,user_id=1,source_date=when.date().isoformat(),saved=False,discarded=False,archive_deleted=False))
        db.add(ResultNotice(user_id=1,kind='letter',result_id=report.encouragement_id,created_at=when))
    db.commit()

@app.post('/fixture/midnight')
def midnight():
    clock['now']=clock['now'].replace(hour=0,minute=0)+timedelta(days=1)
    return {'date':clock['now'].date().isoformat()}

@app.post('/fixture/arrival')
def arrival():
    with Session(engine) as db:
        row=ResultNotice(user_id=1,kind='weekly',result_id=1000+db.query(ResultNotice).count(),created_at=clock['now'])
        db.add(row);db.commit()
    return {'ok':True}
