"""승인된 합성 자료 최대3회. 실행 자체로 외부 API 비용 발생."""
import os
from pathlib import Path
from uuid import uuid4
import argparse
import json
from datetime import datetime,timedelta
from unittest.mock import patch


def verify():
    root=Path('.local-check')/('daily-ai-'+uuid4().hex)
    root.mkdir()
    os.environ['DATABASE_URL']='sqlite:///'+(root/'test.db').resolve().as_posix()
    from sqlalchemy.orm import Session
    from app.core.connection import Base,engine
    from app.models.db.user_model import User
    from app.models.db.chat_message_model import ChatMessage
    from app.models.db.session_summary import GPTSessionSummary
    from app.models.db.study_model import EncouragementReport
    from app.models.db.daily_model import DailyJob
    from app.models.db.writing_model import SummaryRange
    from app.core.daily_migration import migrate_daily_schema
    from app.services import daily_service as svc,daily_ai as ai
    from app.config.settings import settings
    Base.metadata.create_all(engine)
    now=datetime(2026,11,3,22)
    migrate_daily_schema(engine,now.replace(hour=0))
    with Session(engine) as db:
        db.add(User(id=1,username='synthetic-daily-ai',email='synthetic@example.org',nickname='합성검증',hashed_password='unused'))
        db.add(ChatMessage(user_id=1,session_id='synthetic',role='user',message='오늘 미뤄둔 서류 정리를 마쳤어. 조금 피곤하지만 후련해.',timestamp=now-timedelta(minutes=1),turn=1))
        db.commit()
    calls=[]
    ai.MAX_OUTPUT_TOKENS=700
    def generate(kind,*args):
        if len(calls)>=3:raise RuntimeError('Approved call limit reached')
        calls.append({'kind':kind,'started':True})
        result=ai.generate(kind,*args)
        calls[-1]['usage']=ai.last_usage
        return result
    for key in svc.dispatch(engine,now):svc.run_job(engine,key,generate=generate,search=lambda *args:[],index=lambda *args:None,now=now)
    with Session(engine) as db:
        db.add(ChatMessage(user_id=1,session_id='synthetic',role='user',message='저녁에는 잠깐 산책했어. 마음이 한결 가벼워졌어.',timestamp=now+timedelta(hours=1),turn=2));db.commit()
    tomorrow=now.replace(hour=0)+timedelta(days=1)
    for key in svc.dispatch(engine,tomorrow):svc.run_job(engine,key,generate=generate,search=lambda *args:[],index=lambda *args:None,now=tomorrow)
    with Session(engine) as db:
        report={'calls':calls,'model':settings.openai_model,'summaries':db.query(SummaryRange).count(),
                'letters':db.query(EncouragementReport).count(),'jobs':[{'phase':r.phase,'state':r.state,'error':r.error_type} for r in db.query(DailyJob)],
                'database':str(root/'test.db'),'scope':'real AI; synthetic isolated DB; retrieval/index mocked'}
        (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
        if len(calls)!=3 or report['summaries']!=2 or report['letters']!=1:raise RuntimeError('AI integration failed; no automatic extra calls')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--approved-three-calls',action='store_true');args=p.parse_args()
    if not args.approved_three_calls:p.error('사용자 외부AI 승인 필요')
    verify()
