"""실제 제품 템플릿·JS + 격리DB. 기본 합성 AI, 승인 모드에서만 실제 두 요청."""
import os
from pathlib import Path
from uuid import uuid4
Path('.local-check').mkdir(exist_ok=True)
fixture_path=Path('.local-check')/('space-ui-'+str(uuid4())+'.db')
os.environ['DATABASE_URL']='sqlite:///'+fixture_path.resolve().as_posix()
import asyncio
import json
import struct
import zlib
from fastapi import FastAPI,WebSocket,HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from app.core.connection import Base,engine
from app.api.routers import html_router,auth_router,writing_router,study_router
from app.api.routers import access_router
from app.models.db.user_model import User
from app.models.db.writing_model import Writing,WritingOperation
from app.models.db.chat_message_model import ChatMessage
from app.models.db.study_model import DiaryReport
from app.services.auth_service import get_password_hash
from app.services import writing_stream,writing_service
from app.utils.time_utils import get_kst_now

app=FastAPI()
for router in (html_router.router,auth_router.router,writing_router.router,study_router.router,access_router.router):app.include_router(router)
app.mount('/static',StaticFiles(directory='static'),name='static')
Base.metadata.create_all(engine)
with Session(engine) as db:
 for i in (1,2):db.add(User(id=i,username=f'ui-test-{i}',email=f'ui-test-{i}@example.org',nickname=f'화면검증{i}',hashed_password=get_password_hash('UiTest!2026'),registered_at=get_kst_now()))
 db.commit()

faults={'stream':0,'diary':0,'save':0,'edit':0,'photo':0,'save_after_commit':0}
gate=asyncio.Event();gate.set()
calls={'lamp':0,'diary':0,'external':0}
original_generate=writing_router.generate
original_chunks=writing_stream.lamp_chunks
writing_stream.memory_context=lambda *_:[]  # 기존 사용자 검색 인덱스에 접근하지 않는다.
live_mode=os.environ.get('SPACE_LIVE_AI')
live=live_mode in ('approved-two','approved-diary-one')
live_budget=2 if live_mode=='approved-two' else 1

async def chunks(source,memories):
 calls['lamp']+=1
 if live_mode=='approved-two':
  if calls['external']>=live_budget:raise RuntimeError('Approved live budget exhausted')
  if len(source)>1500:raise RuntimeError('Fixture input too large')
  calls['external']+=1
  async for part in original_chunks(source,memories):yield part
  return
 await asyncio.sleep(.3)
 yield '{"bubbles":["막막한 마음에도 한 페이지를 끝냈구나. 정말 애썼어.",'
 await gate.wait()
 await asyncio.sleep(.8)
 if faults['stream']:
  faults['stream']-=1
  raise RuntimeError('Synthetic interrupted response')
 yield '"오늘의 뿌듯함이 네 마음에 오래 남으면 좋겠어."]}'

async def generate(kind,source):
 calls[kind]+=1
 if faults[kind]:faults[kind]-=1;raise RuntimeError('Synthetic generation failure')
 if live:
  if calls['external']>=live_budget:raise RuntimeError('Approved live budget exhausted')
  if len(source)>1500:raise RuntimeError('Fixture input too large')
  calls['external']+=1
  return await original_generate(kind,source)
 await asyncio.sleep(1.5)
 return {'title':'조금씩, 나의 속도로','body':'오늘은 포트폴리오를 조금 수정했다. 계속 고치다 보니 내가 잘하고 있는 건지 확신이 서지 않았다.\n\n그래도 한 페이지를 끝냈다. 작게 느껴질 수도 있지만, 오늘 내가 해낸 일이라 조금 뿌듯했다.\n\n불안한 마음과 뿌듯한 마음이 함께 남은 하루. 오늘은 완성한 한 페이지를 바라보며 하루를 마무리한다.'}
writing_stream.lamp_chunks=chunks
writing_router.generate=generate

@app.middleware('http')
async def failures(request,call_next):
 kind='save' if request.url.path.endswith('/save') else 'photo' if request.url.path.endswith('/photos') else 'edit' if request.method=='PATCH' else None
 if request.method in ('POST','PATCH') and kind and faults[kind]:
  faults[kind]-=1
  return JSONResponse({'detail':'검증용 일시 오류예요. 입력은 그대로 보관했어요.'},status_code=503)
 response=await call_next(request)
 if kind=='save' and faults['save_after_commit']:
  faults['save_after_commit']-=1
  return JSONResponse({'detail':'저장은 처리됐지만 응답 연결이 끊겼어요. 같은 요청으로 확인해 주세요.'},status_code=503)
 return response

@app.post('/fixture/fault/{name}')
def fault(name:str):
 if name not in faults:raise HTTPException(404)
 faults[name]+=1
 return {'armed':name}

@app.post('/fixture/gate/{action}')
def gate_control(action:str):
 if action=='pause':gate.clear()
 else:gate.set()
 return {'open':gate.is_set()}

@app.get('/fixture/status')
def status():
 with Session(engine) as db:
  return {'calls':calls,'live':live,'diaries':db.query(DiaryReport).count(),
          'saved':db.query(DiaryReport).filter_by(state='saved').count(),
          'user_messages':db.query(ChatMessage).filter_by(role='user').count(),
          'assistant_messages':db.query(ChatMessage).filter_by(role='gpt').count(),
          'operations':[{'kind':r.kind,'state':r.state,'source_count':len(r.source_ids),'quota':r.quota_kind} for r in db.query(WritingOperation).all()]}

@app.websocket('/ws/{user_id}')
async def socket(ws:WebSocket,user_id:int):
 await ws.accept()
 await ws.receive_json()
 await ws.close(code=1000)  # 실제 Redis 개인 채널에 합성 계정을 구독시키지 않는다.

def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
png=(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\x80\x00'))+chunk(b'IEND',b''))
Path('.local-check/space-test-photo.png').write_bytes(png)
