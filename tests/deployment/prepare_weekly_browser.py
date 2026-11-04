"""합성 7일/3날짜를 별도 DB에서 실제 AI로 처리 후 지정된 새 시험 계정에만 반영."""
import copy
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

if (os.environ.get('ENVIRONMENT')!='validation' or os.environ.get('DEPLOYMENT_VALIDATION')!='1'
        or os.environ.get('DATABASE_URL')!='sqlite:////data/app.db'
        or os.environ.get('DEPLOYMENT_VALIDATION_REAL_AI')!='1'):
    raise RuntimeError('Only the isolated real AI validation deployment is permitted')
name=sys.argv[1]
if not name.startswith('weeklyscreen') or not name.isalnum():raise ValueError('Invalid synthetic account name')
import validation.runtime
from app.core.connection import engine, Base
from app.models.db.user_model import User
from app.models.db.access_model import AccountAccess
from app.models.db.chat_message_model import ChatMessage
from app.models.db.session_log import SessionLog
from app.models.db.study_model import DiaryAnalysisReport, WeeklyAnalysisReport
from app.models.db.weekly_cycle_model import WeeklyActivation, WeeklyClock, AnalysisJob
from app.models.db.daily_model import ResultNotice
from app.repositories.weekly_analysis_repository import SOURCE_IDS_KEY
from app.services import weekly_cycle_service as service
from app.utils.time_utils import get_kst_now

def values(row, *excluded):
    return {col.name:copy.deepcopy(getattr(row,col.name)) for col in row.__table__.columns if col.name not in excluded}

now=get_kst_now()
end=now.replace(hour=0,minute=0,second=0,microsecond=0)
anchor=end-timedelta(days=7)
logical_now=end-timedelta(minutes=9) # 첫 주 마지막 날23:51, 체험 만료 전
with Session(engine) as db:
    user=db.query(User).filter_by(username=name).one()
    if user.email!=name+'@example.org' or user.nickname!='주간기간검증':raise ValueError('Fixture identity mismatch')
    uid=user.id
    for model in (ChatMessage,DiaryAnalysisReport,WeeklyAnalysisReport,AnalysisJob,ResultNotice):
        if db.query(model).filter_by(user_id=uid).count():raise ValueError('Destination test account must be unused')
    if db.get(WeeklyClock,uid):raise ValueError('Destination already has a weekly clock')
    user_data=values(user)
path=Path('/data')/('weekly-fixture-'+name+'.db')
if path.exists():raise FileExistsError('Fixture DB already exists; it will not be overwritten')
fixture=create_engine('sqlite:///'+str(path))
Base.metadata.create_all(fixture)
with Session(fixture) as db:
    db.add(User(**{**user_data,'registered_at':anchor}))
    db.flush()
    db.add(AccountAccess(user_id=uid,trial_started_at=anchor,trial_expires_at=end,plan='free'))
    db.add(WeeklyActivation(id=1,activated_at=anchor))
    db.add(WeeklyClock(user_id=uid,anchor_date=anchor.date().isoformat()))
    for index,offset in enumerate((0,2,6)):
        date=anchor+timedelta(days=offset,hours=12)
        sid='weekly-fixture-'+name+'-'+str(index)
        db.add(SessionLog(user_id=uid,session_id=sid,start_time=date,end_time=date,emb_success=False))
        db.flush()
        db.add(ChatMessage(user_id=uid,session_id=sid,role='user',timestamp=date,turn=1,
            message=('합성 기간 검사 자료입니다. 작은 정리 작업을 마치고 산책해서 뿌듯했어요.',
                     '합성 기간 검사 자료입니다. 일정이 바빠 조금 피곤했지만 차를 마시며 쉬었어요.',
                     '합성 기간 검사 자료입니다. 계획한 일을 마쳐 후련했고 친구와 안부를 나눴어요.')[index]))
    db.commit()
for stage in range(2):
    for key in service.dispatch(fixture,now=logical_now):
        service.run(fixture,key,now=logical_now)
    print(json.dumps({'fixture_stage':stage+1,'real_ai':True}),flush=True)
with Session(fixture) as source, Session(engine) as target:
    daily=source.query(DiaryAnalysisReport).filter_by(user_id=uid).all()
    weekly=source.query(WeeklyAnalysisReport).filter_by(user_id=uid).all()
    jobs=source.query(AnalysisJob).filter_by(user_id=uid).all()
    assert len(daily)==3 and len(weekly)==1
    assert len(jobs)==8 and all(j.state in ('done','skipped') and j.error_type is None for j in jobs)
    # AI 결과 전체가 검증된 뒤 단일 트랜잭션으로 시험 계정에만 반영한다.
    live=target.get(User,uid)
    live.registered_at=anchor
    access=target.get(AccountAccess,uid)
    access.trial_started_at,access.trial_expires_at,access.onboarding_completed_at=anchor,end,now
    target.add(WeeklyClock(user_id=uid,anchor_date=anchor.date().isoformat()))
    for row in source.query(SessionLog).filter_by(user_id=uid):target.add(SessionLog(**values(row,'id')))
    target.flush()
    chat_ids={}
    for row in source.query(ChatMessage).filter_by(user_id=uid):
        added=ChatMessage(**values(row,'id'));target.add(added);target.flush();chat_ids[row.id]=added.id
    daily_ids={}
    for row in daily:
        added=DiaryAnalysisReport(**values(row,'report_id'));target.add(added);target.flush();daily_ids[row.report_id]=added.report_id
    data=values(weekly[0],'analysis_id')
    data['comprehensive_pattern_result'][SOURCE_IDS_KEY]=[daily_ids[i] for i in data['comprehensive_pattern_result'][SOURCE_IDS_KEY]]
    result=WeeklyAnalysisReport(**data);target.add(result);target.flush();weekly_id=result.analysis_id
    for job in jobs:
        data=values(job)
        data['source_ids']=[(chat_ids if job.kind=='daily' else daily_ids)[i] for i in job.source_ids]
        if job.result_id:data['result_id']=daily_ids[job.result_id] if job.kind=='daily' else weekly_id
        target.add(AnalysisJob(**data))
    target.add(ResultNotice(user_id=uid,kind='weekly',result_id=weekly_id,created_at=logical_now))
    target.commit()
print(json.dumps({'synthetic_user':name,'weekly_id':weekly_id,'daily_reports':3,'active_days':3,
    'anchor':anchor.date().isoformat(),'end':(end-timedelta(days=1)).date().isoformat(),
    'logical_run_at':logical_now.isoformat(),'expired_at':end.isoformat(),
    'system_clock_changed':False,'real_wall_clock_verification':False},ensure_ascii=False),flush=True)
