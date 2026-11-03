"""예약·자정 작업: 짧은 DB 트랜잭션, 고정 입력, 단계별 체크포인트."""
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.db.daily_model import DailySettings, DailyJob, LetterDelivery, ResultNotice, DailyActivation
from app.models.db.user_model import User
from app.models.db.chat_message_model import ChatMessage
from app.models.db.session_log import SessionLog
from app.models.db.session_summary import GPTSessionSummary
from app.models.db.writing_model import SummaryRange
from app.models.db.study_model import EncouragementReport, WeeklyAnalysisReport
from app.services.writing_service import transaction, day_messages, WritingError, owned, format_users
from app.utils.time_utils import get_kst_now
from app.services.access_service import permits


def preference(db, uid, now):
    row = db.get(DailySettings, uid)
    if not row:
        row = DailySettings(user_id=uid,hour=22,previous_hour=22,effective_date=now.date().isoformat(),configured=False)
        db.add(row)
        db.flush()
    return row


def current_hour(row, day):
    return row.previous_hour if day < row.effective_date else row.hour


def settings_payload(row, now):
    return {'hour':row.hour,'today_hour':current_hour(row,now.date().isoformat()),
            'effective_date':row.effective_date,'configured':row.configured}


def update_settings(bind, uid, hour):
    now = get_kst_now()
    with transaction(bind,uid) as db:
        row = preference(db,uid,now)
        today = now.date().isoformat()
        received = db.query(EncouragementReport).filter(EncouragementReport.user_id==uid,
                    func.date(EncouragementReport.timestamp)==today).first()
        job = db.get(DailyJob,f'{uid}:{today}:encouragement')
        # 진행중 작업의 입력/시각은 변경하지 않는다. 성공했으면 다음날 설정.
        if job and job.state == 'running':
            raise WritingError(409,'오늘 편지를 준비 중이에요. 완료 후 시간을 변경해 주세요.')
        row.previous_hour = current_hour(row,today)
        row.hour, row.configured = hour, True
        row.effective_date = (now.date()+timedelta(days=1)).isoformat() if received else today
        if not received and job and (job.state == 'skipped' or job.attempts==0):
            db.delete(job)  # 명시적인 시각변경만 새 예약 점검 허용.
            db.flush()
            job=None
        elif not received and job:
            # 이미 일부 성공한 작업은 원본/결과를 유지하고 변경한 시각에 재개한다.
            target=datetime.combine(now.date(),datetime.min.time()).replace(hour=hour)
            job.retry_at=max(now,target)
        # 지난시각 변경은 변경 순간까지의 입력으로 즉시 점검한다.
        if not received and hour <= now.hour and job is None:
            enqueue(db,uid,today,'encouragement',now,now)
        return settings_payload(row,now)


def enqueue(db, uid, day, phase, cutoff, now):
    key = f'{uid}:{day}:{phase}'
    if db.get(DailyJob,key):
        return
    rows = day_messages(db,uid,day,cutoff)
    delivery = db.query(LetterDelivery).filter_by(user_id=uid,source_date=day).first()
    if phase == 'midnight':
        prior = db.get(DailyJob,f'{uid}:{day}:encouragement')
        reserved = set(prior.source_ids) if prior else set()
        used = {i for r in db.query(SummaryRange).filter_by(user_id=uid,source_date=day) for i in r.source_ids}
        rows = [r for r in rows if r.id not in reserved | used]
    db.add(DailyJob(id=key,user_id=uid,source_date=day,phase=phase,cutoff=cutoff,
        source_ids=[r.id for r in rows],state='pending' if rows else 'skipped',
        summary_indexed=False,letter_done=phase=='midnight' or delivery is not None,attempts=0))


def dispatch(bind, now=None):
    """매분 실행해도 논리 점검은 예약/자정 두 개. 중단된 날짜도 복구한다."""
    now = now or get_kst_now()
    with Session(bind) as db:
        activation = db.get(DailyActivation,1)
        if not activation:
            raise RuntimeError('Daily schema migration required')
        start = activation.activated_at
        users = [r[0] for r in db.query(User.id).all()]
    for uid in users:
        with transaction(bind,uid) as db:
            pref = preference(db,uid,now)
            today = now.date().isoformat()
            cutoff = datetime.combine(now.date(),datetime.min.time()).replace(hour=current_hour(pref,today))
            if now >= cutoff and now >= start:
                enqueue(db,uid,today,'encouragement',cutoff,now)
            # 원본이 있는 마감일만 조회. 실패 작업은 별도로 영속 재시도한다.
            dates = [r[0] for r in db.query(func.date(ChatMessage.timestamp)).filter(
                ChatMessage.user_id==uid,ChatMessage.role=='user',
                ChatMessage.timestamp>=datetime.combine(start.date(),datetime.min.time()),
                ChatMessage.timestamp<datetime.combine(now.date(),datetime.min.time())
            ).distinct()]
            for day in dates:
                enqueue(db,uid,day,'midnight',datetime.fromisoformat(day)+timedelta(days=1),now)
    with Session(bind) as db:
        return [j.id for j in db.query(DailyJob).filter(DailyJob.state.in_(['pending','retry','running']),
                   (DailyJob.retry_at.is_(None)) | (DailyJob.retry_at<=now)).order_by(DailyJob.source_date,DailyJob.phase)]


def checkpoint(bind,uid,key,lease,**values):
    with transaction(bind,uid) as db:
        job = db.get(DailyJob,key)
        if not job or job.lease_token != lease or job.state != 'running':
            raise RuntimeError('Daily lease lost')
        for name,value in values.items():
            setattr(job,name,value)


def save_summary(bind, job, lease, result, now):
    sid = 'day_'+job.source_date.replace('-','')+'_'+job.phase
    with transaction(bind,job.user_id) as db:
        live = db.get(DailyJob,job.id)
        if live.lease_token != lease:
            raise RuntimeError('Daily lease lost')
        existing = db.query(SummaryRange).filter_by(user_id=job.user_id,source_date=job.source_date,phase=job.phase).first()
        if not existing:
            db.add(SummaryRange(id=str(uuid4()),user_id=job.user_id,source_date=job.source_date,
                phase=job.phase,source_ids=job.source_ids,summary=result['summary'],created_at=now))
        if not db.query(GPTSessionSummary).filter_by(user_id=job.user_id,session_id=sid).first():
            # 날짜 구간 자체의 로그. 원문ID는 DailyJob/SummaryRange와 함께 연결된다.
            db.add(SessionLog(user_id=job.user_id,session_id=sid,
                start_time=datetime.fromisoformat(job.source_date),end_time=job.cutoff,emb_success=False))
            db.flush()
            db.add(GPTSessionSummary(user_id=job.user_id,session_id=sid,summary=result['summary'],
                key_sentence=result.get('key_sentence',''),keywords=result.get('keywords',[]),
                created_at=datetime.fromisoformat(job.source_date)))
        live.summary_result = result
    return sid


def run_job(bind,key,generate=None,search=None,index=None,now=None):
    from app.services import daily_ai
    generate,search,index = generate or daily_ai.generate,search or daily_ai.search,index or daily_ai.index_summary
    fixed_clock = now is not None
    now = now or get_kst_now()
    with Session(bind) as db:
        found = db.get(DailyJob,key)
        if not found:
            return
        uid = found.user_id
    with transaction(bind,uid) as db:
        job = db.get(DailyJob,key)
        if job.state in ('done','skipped') or (job.retry_at and job.retry_at>now):
            return
        if job.state=='running' and job.lease_until and job.lease_until>now:
            return
        lease = str(uuid4())
        job.state,job.lease_token,job.lease_until = 'running',lease,now+timedelta(minutes=15)
        job.attempts += 1
        nickname = db.get(User,uid).nickname
        source = format_users(db.query(ChatMessage).filter(ChatMessage.user_id==uid,
            ChatMessage.role=='user',ChatMessage.id.in_(job.source_ids)).order_by(ChatMessage.timestamp,ChatMessage.id).all())
        db.flush()
    errors=[]
    if not job.summary_result:
        try:
            result = generate('summary',source)
            checkpoint(bind,uid,key,lease,summary_result=result)
            job.summary_result = result
        except Exception as exc:
            errors.append(type(exc).__name__)
    summary_saved=False
    if job.summary_result:
        try:
            save_summary(bind,job,lease,job.summary_result,now)
            summary_saved=True
        except Exception as exc:
            errors.append(type(exc).__name__)
    # 오늘을 벗어나면 편지는 신규 생성/발행하지 않고 요약 복구만 한다.
    if job.phase=='encouragement' and not job.letter_done:
        with Session(bind) as db:
            allowed = permits(db, uid, 'encouragement', now if fixed_clock else get_kst_now())
        if job.source_date!=now.date().isoformat() or not allowed:
            checkpoint(bind,uid,key,lease,letter_done=True)
            job.letter_done=True
        else:
            try:
                if not job.letter_result:
                    memories=[]
                    if job.summary_result:
                        try:
                            memories=search(bind,uid,job.summary_result['summary'],job.source_date)
                        except Exception as exc:
                            errors.append('search_'+type(exc).__name__)
                    result=generate('letter',source,nickname,memories)
                    checkpoint(bind,uid,key,lease,letter_result=result)
                    job.letter_result=result
                # API 중 자정 통과도 생성시각이 아닌 저장 직전 실제시각으로 차단한다.
                save_now = now if fixed_clock else get_kst_now()
                if save_now.date().isoformat()==job.source_date:
                    with transaction(bind,uid) as db:
                        live=db.get(DailyJob,key)
                        if live.lease_token!=lease:
                            raise RuntimeError('Daily lease lost')
                        # 생성 도중 체험/이용 기간 종료 또는 기능 변경도 발행 전에 확인.
                        old=db.query(LetterDelivery).filter_by(user_id=uid,source_date=job.source_date).first()
                        if not old and permits(db,uid,'encouragement',save_now):
                            report=EncouragementReport(user_id=uid,encourage_content=job.letter_result['encourage_content'],
                                music=[],singer=[],timestamp=save_now)
                            db.add(report);db.flush()
                            db.add(LetterDelivery(id=report.encouragement_id,user_id=uid,source_date=job.source_date,
                                saved=False,discarded=False,archive_deleted=False))
                            db.add(ResultNotice(user_id=uid,kind='letter',result_id=report.encouragement_id,created_at=save_now))
                        live.letter_done=True
                else:
                    checkpoint(bind,uid,key,lease,letter_done=True)
                job.letter_done=True
            except Exception as exc:
                errors.append(type(exc).__name__)
    if summary_saved and not job.summary_indexed:
        try:
            sid='day_'+job.source_date.replace('-','')+'_'+job.phase
            index(uid,sid,job.source_date,job.summary_result)
            checkpoint(bind,uid,key,lease,summary_indexed=True)
            job.summary_indexed=True
        except Exception as exc:
            errors.append(type(exc).__name__)
    done=summary_saved and job.summary_indexed and job.letter_done
    checkpoint(bind,uid,key,lease,state='done' if done else 'retry',lease_until=None,
        retry_at=None if done else now+timedelta(minutes=min(60,2**min(job.attempts,6))),
        error_type=','.join(errors)[:100] or None)


def sync_notices(db,uid):
    # 주간 생성 경로를 바꾸지 않고 기존 성공 결과도 영속 알림으로 복원한다.
    for row in db.query(WeeklyAnalysisReport).filter_by(user_id=uid):
        if not db.query(ResultNotice).filter_by(user_id=uid,kind='weekly',result_id=row.analysis_id).first():
            db.add(ResultNotice(user_id=uid,kind='weekly',result_id=row.analysis_id,created_at=row.timestamp))


def publish_notices(bind,publish):
    """커밋된 결과만 발행. 실패 시 다음 디스패치에서 재전송한다."""
    import json
    with Session(bind) as db:
        rows=db.query(ResultNotice).filter(ResultNotice.published_at.is_(None)).all()
        pending=[(r.id,r.user_id,r.kind,r.result_id,r.created_at.date().isoformat()) for r in rows]
    for key,uid,kind,result_id,day in pending:
        try:
            message={'type':'encourage_available' if kind=='letter' else 'seven_day_report',
                     'result_id':result_id,'analysis_id':result_id,'date':day,'notice_id':key}
            publish(f'user_{uid}_'+('encourage' if kind=='letter' else 'report'),json.dumps(message))
            with transaction(bind,uid) as db:
                row=db.get(ResultNotice,key)
                row.published_at=get_kst_now()
        except Exception:
            # 폴링 조회와 영속 알림은 유지된다. 원문/비밀값을 오류에 싣지 않는다.
            continue


def letter_payload(db,row):
    report=db.get(EncouragementReport,row.id)
    return {'id':row.id,'date':row.source_date,'body':report.encourage_content,
            'saved':row.saved and not row.archive_deleted,'discarded':row.discarded,
            'archive_deleted':row.archive_deleted,
            'viewed':row.viewed_at is not None}


def change_letter(bind,uid,key,action):
    with transaction(bind,uid) as db:
        row=owned(db,LetterDelivery,key,uid)
        if row.archive_deleted and row.source_date!=get_kst_now().date().isoformat():
            if action=='archive-delete':return {'id':key,'archive_deleted':True}
            raise WritingError(404,'삭제한 편지입니다.')
        if row.discarded:
            if action=='discard': return {'id':key,'discarded':True}
            raise WritingError(404,'편지를 찾을 수 없습니다.')
        if action=='view':row.viewed_at=row.viewed_at or get_kst_now()
        elif action=='save':
            if row.archive_deleted:raise WritingError(409,'보관함에서 삭제한 편지예요.')
            row.saved=True
        elif action=='discard':
            if row.saved:raise WritingError(409,'이미 보관한 편지예요. 보관함에서 삭제해 주세요.')
            row.discarded=True
        elif action=='archive-delete':
            if not row.saved:raise WritingError(404,'보관한 편지가 없습니다.')
            row.archive_deleted=True
        return letter_payload(db,row)
