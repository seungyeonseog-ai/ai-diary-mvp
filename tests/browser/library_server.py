"""서재 실제 UI 검증 서버. 매 실행 별도 DB, 외부 AI/Redis 검색·발행 없음."""
import os
from pathlib import Path
from uuid import uuid4
os.environ['DATABASE_URL']='sqlite:///'+(Path('.local-check')/f'library-ui-{uuid4()}.db').resolve().as_posix()
from datetime import timedelta,datetime
from fastapi import FastAPI,WebSocket,HTTPException,Depends
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from app.core.connection import Base,engine
from app.api.routers import html_router,auth_router,writing_router,library_router
from app.models.db.user_model import User
from app.models.db.study_model import DiaryReport
from app.models.db.writing_model import Writing
from app.services.auth_service import get_password_hash
from app.utils.time_utils import get_kst_now,KST
from app.api.dependencies.auth_dependencies import get_current_user
app=FastAPI()
for router in (html_router.router,auth_router.router,writing_router.router,library_router.router):app.include_router(router)
app.mount('/static',StaticFiles(directory='static'),name='static')
Base.metadata.create_all(engine)
with Session(engine) as db:
 for uid in (1,2):db.add(User(id=uid,username=f'library-test-{uid}',email=f'library-{uid}@example.org',nickname=f'서재검증{uid}',hashed_password=get_password_hash('Library!2026'),registered_at=get_kst_now()))
 now=get_kst_now()
 for index in range(12):
  db.add(DiaryReport(diary_id=index+1,user_id=1,title=['조금씩, 나의 속도로','잠시 쉬어가도 괜찮아','작은 용기를 모은 하루','따뜻한 차 한 잔','오늘의 마음을 남기며'][index%5],content='화면 검증을 위한 합성 일기입니다.\n\n작은 일을 하나 마치고 나니 마음이 편안해졌다. 오늘의 수고를 차분히 돌아보며 하루를 마무리한다.',timestamp=now-timedelta(days=index)))
 db.add(DiaryReport(diary_id=20,user_id=1,title='윤일의 기록',content='합성 윤일 기록입니다.',timestamp=datetime(2024,2,29,12)))
 db.commit()
faults={'read':0,'edit':0,'delete':0,'photo':0}
@app.middleware('http')
async def failures(request,call_next):
 kind='read' if request.url.path.startswith('/library-data/') else 'edit' if request.method=='PATCH' else 'delete' if request.method=='DELETE' else 'photo' if request.url.path.endswith('/photos') and request.method=='POST' else None
 if kind and faults[kind]:
  faults[kind]-=1;return JSONResponse({'detail':'검증용 일시 오류예요. 다시 시도해 주세요.'},status_code=503)
 return await call_next(request)
@app.post('/fixture/fault/{name}')
def fault(name:str):
 if name not in faults:raise HTTPException(404)
 faults[name]+=1;return {'armed':name}
@app.get('/fixture/status')
def status():
 with Session(engine) as db:return {'diaries':db.query(DiaryReport).count(),'saved':db.query(DiaryReport).filter_by(state='saved').count(),'writings':db.query(Writing).count(),'external_ai_calls':0}
@app.get('/study/status')
def study(user=Depends(get_current_user)):
 now=get_kst_now();state='ready' if user.id==1 else 'unavailable';return {'user_id':user.id,'server_now':now.replace(tzinfo=KST).isoformat(),'server_date':now.date().isoformat(),'encouragement':{'state':state},'weekly':{'state':state}}
@app.get('/study/weekly/latest')
def weekly():
 today=get_kst_now().date();return {'diary_analyses':[{'date_str':(today-timedelta(days=i)).isoformat(),'scores':[.2+i*.05,.3]} for i in (6,4,0)]}
@app.websocket('/ws/{uid}')
async def socket(ws:WebSocket,uid:int):
 await ws.accept();await ws.receive_json();await ws.close(code=1000)

# 서재 검사 중 실수로 생성 API를 눌러도 외부 AI를 호출하지 않는다.
async def no_ai(*args,**kwargs):raise HTTPException(409,'서재 검증에서는 AI 생성을 호출하지 않습니다.')
writing_router.generate=no_ai
