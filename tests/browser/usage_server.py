"""묶음2 분리본 전용 서버. AI·검색은 합성이며 실제8000에 연결하지 않는다."""
from sqlalchemy.orm import Session
from tests.browser import trial_access_server as trial
from app.models.db.writing_model import Writing, WritingOperation
from app.services import writing_service

app,engine,clock,space=trial.app,trial.engine,trial.clock,trial.space
space.faults['complete']=0
original_complete=writing_service.complete_operation


def complete_with_fault(bind,uid,key,lease,result,**kwargs):
    if space.faults['complete']:
        with Session(bind) as db:
            operation=db.get(WritingOperation,key)
            is_lamp=operation is not None and operation.kind=='lamp'
        if is_lamp:
            space.faults['complete']-=1
            raise RuntimeError('Synthetic result persistence failure')
    return original_complete(bind,uid,key,lease,result,**kwargs)


writing_service.complete_operation=complete_with_fault


@app.get('/fixture/usage-evidence')
def evidence():
    with Session(engine) as db:
        today=clock['now'].date().isoformat()
        rows=db.query(Writing).filter_by(source_date=today,state='active').all()
        current=[{'user_id':row.user_id,'writing_id':row.id,
                  'quota':writing_service.quota(db,row.user_id,row,clock['now'])} for row in rows]
        operations=[{'id':row.id,'request_id':row.client_id,'user_id':row.user_id,
                     'date':row.source_date,'quota_kind':row.quota_kind,'state':row.state,
                     'has_generated_result':row.result is not None}
                    for row in db.query(WritingOperation).order_by(WritingOperation.created_at,WritingOperation.id)]
    return {'source':'bundle2-only','server_now':clock['now'].isoformat(),'current':current,
            'operations':operations,'calls':dict(space.calls),'external_ai_calls':space.calls['external']}
