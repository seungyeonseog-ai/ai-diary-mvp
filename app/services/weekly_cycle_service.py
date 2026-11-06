"""첫 대화 날짜부터 계정별 5일/기존 7일 고정 기간. 매일23:50 원본은 작업등록 전에 고정한다."""
from datetime import datetime,timedelta
from uuid import uuid4
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.db.weekly_cycle_model import WeeklyActivation,WeeklyClock,AnalysisJob
from app.models.db.study_model import DiaryAnalysisReport,WeeklyAnalysisReport
from app.models.db.chat_message_model import ChatMessage
from app.models.db.user_model import User
from app.models.db.daily_model import ResultNotice
from app.services.writing_service import transaction,day_messages,format_users
from app.repositories.weekly_analysis_repository import SOURCE_IDS_KEY
from app.utils.time_utils import get_kst_now
from app.services.access_service import permits,cycle_days


def cutoff(day):return datetime.fromisoformat(day).replace(hour=23,minute=50)


def dispatch(bind,now=None):
    now=now or get_kst_now()
    with Session(bind) as db:
        activation=db.get(WeeklyActivation,1)
        if not activation:raise RuntimeError('Weekly migration required')
        activated=activation.activated_at
        users=[x[0] for x in db.query(User.id)]
    for uid in users:
        with transaction(bind,uid) as db:
            clock=db.get(WeeklyClock,uid)
            if not clock:
                first=db.query(ChatMessage).filter(ChatMessage.user_id==uid,ChatMessage.role=='user',ChatMessage.timestamp>=activated).order_by(ChatMessage.timestamp,ChatMessage.id).first()
                if not first:continue
                clock=WeeklyClock(user_id=uid,anchor_date=first.timestamp.date().isoformat());db.add(clock);db.flush()
            # 늦게 재기동해도 첫날부터 원래 23:50 경계를 보존한다.
            day=datetime.fromisoformat(clock.anchor_date)
            while cutoff(day.date().isoformat())<=now:
                source_date=day.date().isoformat();key=f'{uid}:daily:{source_date}'
                if not db.get(AnalysisJob,key):
                    rows=day_messages(db,uid,source_date,cutoff(source_date))
                    db.add(AnalysisJob(id=key,user_id=uid,kind='daily',start_date=source_date,end_date=source_date,
                        source_ids=[r.id for r in rows],state='pending' if rows else 'skipped',attempts=0))
                    db.flush()
                day+=timedelta(days=1)
            period=cycle_days(db,uid)
            start=datetime.fromisoformat(clock.anchor_date)
            while cutoff((start+timedelta(days=period-1)).date().isoformat())<=now:
                end=(start+timedelta(days=period-1)).date().isoformat();key=f'{uid}:weekly:{end}'
                if not db.get(AnalysisJob,key):
                    daily=db.query(AnalysisJob).filter(AnalysisJob.user_id==uid,AnalysisJob.kind=='daily',
                        AnalysisJob.end_date>=start.date().isoformat(),AnalysisJob.end_date<=end).order_by(AnalysisJob.end_date).all()
                    active=[j for j in daily if j.source_ids]
                    if len(active)<3 or not permits(db,uid,'weekly',now):
                        db.add(AnalysisJob(id=key,user_id=uid,kind='weekly',start_date=start.date().isoformat(),end_date=end,source_ids=[],state='skipped',attempts=0))
                    elif len(daily)==period and all(j.state in ('done','skipped') for j in daily):
                        db.add(AnalysisJob(id=key,user_id=uid,kind='weekly',start_date=start.date().isoformat(),end_date=end,source_ids=[j.result_id for j in active],state='pending',attempts=0))
                start+=timedelta(days=period)
    with Session(bind) as db:return [r.id for r in db.query(AnalysisJob).filter(AnalysisJob.state.in_(['pending','retry','running']),
        (AnalysisJob.retry_at.is_(None))|(AnalysisJob.retry_at<=now)).order_by(AnalysisJob.end_date,AnalysisJob.kind)]


def checkpoint(bind,uid,key,lease,**values):
    with transaction(bind,uid) as db:
        row=db.get(AnalysisJob,key)
        if row.state!='running' or row.lease_token!=lease:raise RuntimeError('Analysis lease lost')
        for k,v in values.items():setattr(row,k,v)


def run(bind,key,generate=None,now=None):
    from app.services.weekly_cycle_ai import generate as real_generate,validate_daily,validate_weekly
    fixed_clock=now is not None
    generate=generate or real_generate;now=now or get_kst_now()
    with Session(bind) as db:
        job=db.get(AnalysisJob,key)
        if not job:return
        uid=job.user_id
    with transaction(bind,uid) as db:
        job=db.get(AnalysisJob,key)
        if job.state in ('done','skipped') or (job.retry_at and job.retry_at>now) or (job.state=='running' and job.lease_until and job.lease_until>now):return
        if job.kind=='weekly' and not permits(db,uid,'weekly',now):
            job.state='skipped';job.lease_until=None;return
        lease=str(uuid4());job.state='running';job.lease_token=lease;job.lease_until=now+timedelta(minutes=10);job.attempts+=1
        if job.kind=='daily':
            source=format_users(db.query(ChatMessage).filter(ChatMessage.user_id==uid,ChatMessage.role=='user',ChatMessage.id.in_(job.source_ids)).order_by(ChatMessage.timestamp,ChatMessage.id).all())
        else:
            rows=db.query(DiaryAnalysisReport).filter(DiaryAnalysisReport.user_id==uid,DiaryAnalysisReport.report_id.in_(job.source_ids)).order_by(DiaryAnalysisReport.date_str).all()
            if len(rows)!=len(job.source_ids):raise ValueError('Missing weekly sources')
            source=[{'date':r.date_str,'emotions':r.emotions,'scores':r.scores,'keywords':r.keywords,'summary':r.summary} for r in rows]
    try:
        result=job.result or {}
        if job.kind=='daily':
            if not result:
                result=validate_daily(generate('daily',source));checkpoint(bind,uid,key,lease,result=result)
        else:
            for phase in ('emotion','keyword','comprehensive'):
                if phase not in result:
                    with Session(bind) as db:
                        if not permits(db,uid,'weekly',now if fixed_clock else get_kst_now()):
                            raise PermissionError('Weekly access expired during generation')
                    value=validate_weekly(phase,generate(phase,{'days':source,'period_start':job.start_date,'period_end':job.end_date,'period_days':(datetime.fromisoformat(job.end_date)-datetime.fromisoformat(job.start_date)).days+1,'previous':result}))
                    result={**result,phase:value};checkpoint(bind,uid,key,lease,result=result)
        with transaction(bind,uid) as db:
            live=db.get(AnalysisJob,key)
            if live.state!='running' or live.lease_token!=lease:raise RuntimeError('Analysis lease lost')
            if live.result_id:
                live.state='done';return
            if job.kind=='weekly' and not permits(db,uid,'weekly',now if fixed_clock else get_kst_now()):
                live.state='skipped';live.lease_until=None;return
            if job.kind=='daily':
                row=DiaryAnalysisReport(user_id=uid,date_str=job.end_date,timestamp=datetime.fromisoformat(job.end_date),
                    emotions=result['emotions'],scores=result['scores'],keywords=result['keywords'],keyword_descriptions=result['keyword_descriptions'],summary=result['summary'],is_used_in_weekly=False)
            else:
                row=WeeklyAnalysisReport(user_id=uid,week_start_date=datetime.fromisoformat(job.start_date),week_end_date=datetime.fromisoformat(job.end_date),used_dates=[d['date'] for d in source],
                    emotion_trend_result=result['emotion'],keyword_pattern_result=result['keyword'],comprehensive_pattern_result={**result['comprehensive'],SOURCE_IDS_KEY:job.source_ids,'_schema_version':2},timestamp=now)
            db.add(row);db.flush();live.result_id=row.report_id if job.kind=='daily' else row.analysis_id
            if job.kind=='weekly':
                db.add(ResultNotice(user_id=uid,kind='weekly',result_id=row.analysis_id,created_at=now))
                db.query(DiaryAnalysisReport).filter(DiaryAnalysisReport.user_id==uid,DiaryAnalysisReport.report_id.in_(job.source_ids)).update({'is_used_in_weekly':True},synchronize_session=False)
            live.state='done';live.lease_until=None;live.retry_at=None;live.error_type=None
    except Exception as exc:
        expired = isinstance(exc, PermissionError)
        checkpoint(bind,uid,key,lease,state='skipped' if expired else 'retry',lease_until=None,
                   retry_at=None if expired else now+timedelta(minutes=min(60,2**min(job.attempts,6))),error_type=type(exc).__name__)


def status(db,uid,now=None):
    now=now or get_kst_now();clock=db.get(WeeklyClock,uid)
    period=cycle_days(db,uid)
    if not clock:return {'state':'waiting_dialogue','days':0,'period_days':period}
    anchor=datetime.fromisoformat(clock.anchor_date).date();index=max(0,(now.date()-anchor).days//period);start=anchor+timedelta(days=period*index);end=start+timedelta(days=period-1)
    rows=db.query(ChatMessage.timestamp).filter(ChatMessage.user_id==uid,ChatMessage.role=='user',ChatMessage.timestamp>=datetime.combine(start,datetime.min.time()),ChatMessage.timestamp<cutoff(end.isoformat())).all()
    days=len({r[0].date() for r in rows if r[0]<cutoff(r[0].date().isoformat())})
    failed=db.query(AnalysisJob).filter(AnalysisJob.user_id==uid,AnalysisJob.state=='retry').first()
    return {'state':'retry' if failed else 'waiting_period','days':days,'period_days':period,'start':start.isoformat(),'end':end.isoformat()}
