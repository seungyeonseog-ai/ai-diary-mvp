"""실제 앱 화면/라우터를 쓰는 격리 브라우저 검증 서버. 운영 DB·Redis·AI 사용 없음."""
import os
os.environ.update(DATABASE_URL='sqlite:///:memory:', SECRET_KEY='bundle3-browser-only-secret',
                  OPENAI_API_KEY='test-only-no-network', PYTHONUTF8='1')
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import uvicorn
from app.core.connection import Base, get_db
from app.core.token_utils import encode_token, decode_token
from app.api.routers import study_router as study
from app.services import study_state_service as state
from app.models.db.user_model import User
from app.models.db.session_log import SessionLog
from app.models.db.chat_message_model import ChatMessage
from app.models.db.study_model import DiaryReport, EncouragementReport, WeeklyAnalysisReport, DiaryAnalysisReport

engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread':False})
Base.metadata.create_all(engine)
Sessions = sessionmaker(bind=engine)
clock = [datetime(2026,10,29,12)]
mode = ['ready']
sockets = set()
requests = {'status':0, 'letter':0, 'weekly':0}
with Sessions() as db:
    db.add(User(id=1, username='browser-synthetic', nickname='합성 검증 계정',
                email='browser@example.org', hashed_password='unused'))
    db.add(SessionLog(session_id='bundle3-browser', user_id=1, start_time=clock[0]))
    db.commit()


def seed(kind):
    base = datetime(2026,10,29,12)
    clock[0] = base + timedelta(days=1) if kind == 'nextday' else base
    with Sessions() as db:
        for model in (ChatMessage, DiaryReport, EncouragementReport, WeeklyAnalysisReport, DiaryAnalysisReport):
            db.query(model).delete()
        if kind != 'nextday':
            db.add(ChatMessage(user_id=1,session_id='bundle3-browser',role='user',message='합성 '*100,
                              timestamp=base,turn=1))
        dates = [(base-timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7,0,-1)]
        for i, day in enumerate(dates):
            db.add(DiaryAnalysisReport(user_id=1,date_str=day,timestamp=datetime.fromisoformat(day),
                emotions=['기쁨','평온','기대'],scores=[0.3+i*0.05,0.3,0.2],
                keywords=['성장','휴식','연결'],keyword_descriptions=['합성 설명']*3,
                summary='합성 요약',is_used_in_weekly=kind!='pending'))
        if kind != 'pending':
            when = base-timedelta(days=1) if kind=='yesterday' else base
            db.add(EncouragementReport(encouragement_id=10 if kind=='new' else 9,user_id=1,
                timestamp=when,music=[],singer=[],encourage_content=(
                    '두 번째 합성 응원 편지' if kind=='new' else '오늘의 합성 응원 편지')+
                    '\n오늘도 자신의 속도로 걸어온 하루를 응원해요.\n<img src=x onerror=alert(1)>'))
            db.add(WeeklyAnalysisReport(analysis_id=42 if kind=='new' else 41,user_id=1,
                week_start_date=datetime.fromisoformat(dates[0]), week_end_date=datetime.fromisoformat(dates[-1]),
                timestamp=base, used_dates=dates,
                emotion_trend_result={'trend':'차분하게 회복하는 흐름','dominant_emotion':'평온',
                                      'recommendation':'잠깐의 휴식을 이어가 보세요.','emotion_stability':0.7},
                keyword_pattern_result={'main_themes':['성장','휴식','연결'],
                                        'insights':'작은 휴식이 하루의 균형을 도왔어요.\n합성 자료로 확인하는 주간 결과입니다.'},
                comprehensive_pattern_result={'overall_assessment':'회복하는 한 주였어요.',
                                              'life_satisfaction':0.6,'stress_level':0.3}))
        db.commit()


app = FastAPI()
app.include_router(study.router)
def isolated_db():
    with Sessions() as db:
        yield db
app.dependency_overrides[get_db] = isolated_db
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
app.mount('/templates',StaticFiles(directory=ROOT/'templates'),name='templates')


@app.middleware('http')
async def controlled_failure(request, call_next):
    if request.url.path == '/study/status':
        requests['status'] += 1
        if mode[0] == 'error': return JSONResponse({'detail':'합성 상태 조회 장애'},status_code=503)
    if request.url.path == '/study/encourage': requests['letter'] += 1
    if request.url.path.startswith('/study/seven-day-report/'): requests['weekly'] += 1
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/')
def fixture():
    return FileResponse(Path(__file__).with_name('bundle3.html'))


@app.get('/test/app',response_class=HTMLResponse)
def actual_app():
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>격리 앱 화면</title><body>' + \
        (ROOT/'templates/mypage_edit.html').read_text(encoding='utf-8') + '</body></html>'


@app.get('/test/session')
def session():
    return {'access_token':encode_token(1),'user_id':1}


@app.post('/test/scenario/{kind}')
async def scenario(kind:str):
    if kind not in {'ready','yesterday','nextday','pending','error','reconnect'}:
        return JSONResponse({'detail':'unknown scenario'},status_code=400)
    mode[0] = 'ready' if kind=='reconnect' else kind
    seed('new' if kind=='reconnect' else kind)
    if kind=='reconnect':
        for socket in list(sockets): await socket.close(code=1012)
    return {'scenario':kind,'server_date':clock[0].date().isoformat(),'requests':requests.copy()}


@app.get('/test/observed')
def observed():
    return {'requests':requests.copy(),'websockets':len(sockets)}


@app.websocket('/ws/{uid}')
async def local_socket(socket:WebSocket,uid:int):
    await socket.accept()
    try:
        frame=await socket.receive_json()
        if decode_token(frame.get('token','')).get('user_id') != uid:
            await socket.close(code=1008)
            return
        sockets.add(socket)
        while True:
            await socket.receive_text()
            await socket.send_json({'type':'pong'})
    except Exception:
        pass
    finally:
        sockets.discard(socket)


if __name__=='__main__':
    seed('ready')
    with patch.object(state,'get_kst_now',side_effect=lambda:clock[0]), \
         patch.object(study,'get_kst_now',side_effect=lambda:clock[0]), \
         patch.object(study.redis,'Redis',return_value=Mock()):
        uvicorn.run(app,host='127.0.0.1',port=8012,log_level='warning')
