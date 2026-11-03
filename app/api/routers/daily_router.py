"""본인 예약·편지·서재 숫자 알림. GET 조회는 생성하지 않는다."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
from app.core.connection import get_db
from app.api.dependencies.auth_dependencies import get_current_user
from app.models.db.user_model import User
from app.models.db.daily_model import DailyJob, DailySettings, LetterDelivery, ResultNotice
from app.services import daily_service as service
from app.services.writing_service import transaction, WritingError, owned
from app.utils.time_utils import get_kst_now

router=APIRouter(prefix='/daily',tags=['daily'])


class SettingInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    hour:int=Field(ge=0,le=23,strict=True)


class SeenInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    through_id:int=Field(ge=0,strict=True)


def execute(fn,*args):
    try:return fn(*args)
    except WritingError as exc:raise HTTPException(exc.status,exc.message) from None


@router.get('/settings')
def settings(db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    with transaction(db.get_bind(),user.id) as session:
        return service.settings_payload(service.preference(session,user.id,get_kst_now()),get_kst_now())


@router.put('/settings')
def update(data:SettingInput,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    return execute(service.update_settings,db.get_bind(),user.id,data.hour)


@router.get('/inbox')
def inbox(db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    now=get_kst_now();day=now.date().isoformat()
    row=db.query(LetterDelivery).filter_by(user_id=user.id,source_date=day,discarded=False).first()
    pref=db.get(DailySettings,user.id)
    hour=service.current_hour(pref,day) if pref else 22
    job=db.get(DailyJob,f'{user.id}:{day}:encouragement')
    state='ready' if row else 'discarded' if job and job.letter_done else 'skipped' if job and job.state=='skipped' else 'waiting_time' if now.hour<hour else 'pending'
    return {'server_date':day,'state':state,'hour':hour,'letter':service.letter_payload(db,row) if row else None}


@router.get('/letters')
def letters(view:str='pending',db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    if view not in ('pending','archive'):raise HTTPException(422,'목록을 선택해 주세요.')
    query=db.query(LetterDelivery).filter_by(user_id=user.id,discarded=False)
    query=query.filter_by(saved=True,archive_deleted=False) if view=='archive' else query.filter_by(saved=False)
    rows=query.order_by(LetterDelivery.source_date.desc()).all()
    return {'items':[{'id':r.id,'date':r.source_date,'viewed':r.viewed_at is not None} for r in rows]}


@router.get('/letters/{key}')
def letter(key:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    row=execute(owned,db,LetterDelivery,key,user.id)
    if row.discarded:raise HTTPException(404,'편지를 찾을 수 없습니다.')
    if row.archive_deleted and row.source_date!=get_kst_now().date().isoformat():raise HTTPException(404,'삭제한 편지입니다.')
    return service.letter_payload(db,row)


@router.post('/letters/{key}/{action}')
def action(key:int,action:str,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    if action not in ('view','save','discard','archive-delete'):raise HTTPException(404)
    return execute(service.change_letter,db.get_bind(),user.id,key,action)


@router.get('/notices')
def notices(db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    with transaction(db.get_bind(),user.id) as session:
        service.sync_notices(session,user.id);session.flush()
        rows=session.query(ResultNotice).filter_by(user_id=user.id).order_by(ResultNotice.id).all()
        return {'through_id':max((r.id for r in rows),default=0),'count':sum(r.badge_seen_at is None for r in rows),
                'items':[{'id':r.id,'kind':r.kind,'result_id':r.result_id,'seen':r.badge_seen_at is not None} for r in rows]}


@router.post('/notices/seen')
def seen(data:SeenInput,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    with transaction(db.get_bind(),user.id) as session:
        session.query(ResultNotice).filter(ResultNotice.user_id==user.id,ResultNotice.id<=data.through_id,
            ResultNotice.badge_seen_at.is_(None)).update({'badge_seen_at':get_kst_now()},synchronize_session=False)
    return {'ok':True}
