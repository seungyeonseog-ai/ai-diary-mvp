"""승인된 격리 합성검사 최대6회. 실행시 외부AI 비용 발생."""
import argparse,os,json
from pathlib import Path
from uuid import uuid4
from datetime import datetime


def verify():
    root=Path('.local-check')/('weekly-ai-'+uuid4().hex);root.mkdir()
    os.environ['DATABASE_URL']='sqlite:///'+(root/'test.db').resolve().as_posix()
    from sqlalchemy.orm import Session
    from app.core.connection import Base,engine
    from app.models.db.user_model import User
    from app.models.db.chat_message_model import ChatMessage
    from app.models.db.session_log import SessionLog
    from app.models.db.writing_model import Writing
    from app.models.db.study_model import DiaryAnalysisReport,WeeklyAnalysisReport
    from app.models.db.daily_model import ResultNotice
    from app.core.weekly_migration import migrate_weekly_schema
    from app.services import weekly_cycle_service as svc,weekly_cycle_ai as ai
    Base.metadata.create_all(engine);migrate_weekly_schema(engine,datetime(2026,11,1))
    with Session(engine) as db:
        db.add(User(id=1,username='weekly-ai-synthetic',email='weekly@example.org',nickname='합성검증',hashed_password='unused'))
        for day,message in [(1,'미뤘던 서류 정리를 마쳤어. 피곤하지만 후련해.'),(3,'잠깐 산책하고 따뜻한 차를 마셨어. 마음이 차분해졌어.'),(7,'친구와 만나 이야기를 나눴어. 혼자 고민할 때보다 편안해졌어.')]:
            db.add(ChatMessage(user_id=1,session_id='synthetic',role='user',turn=1,message=message,timestamp=datetime(2026,11,day,12)))
        db.commit()
    calls=[]
    def generate(kind,data):
        if len(calls)>=6:raise RuntimeError('Approved call limit')
        calls.append({'kind':kind})
        result=ai.generate(kind,data);calls[-1]['usage']=ai.last_usage;return result
    for _ in range(2):
        for key in svc.dispatch(engine,datetime(2026,11,7,23,51)):svc.run(engine,key,generate=generate,now=datetime(2026,11,7,23,51))
    with Session(engine) as db:
        result={'calls':calls,'daily_count':db.query(DiaryAnalysisReport).count(),'weekly_count':db.query(WeeklyAnalysisReport).count(),'database':str(root/'test.db')}
        (root/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
        assert len(calls)==6 and result['daily_count']==3 and result['weekly_count']==1,'No automatic extra calls'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--approved-six-calls',action='store_true')
    if not p.parse_args().approved_six_calls:p.error('사용자 승인 필요')
    verify()
