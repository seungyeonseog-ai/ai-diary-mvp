"""5묶음 실제 화면: 합성 AI·격리 DB, 사용자 서비스/외부 AI 무사용."""
import sys,json,asyncio,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bundle3_server as fixture
from unittest.mock import patch,Mock,AsyncMock
from fastapi.responses import FileResponse,HTMLResponse,Response
from app.api.routers import chat_message_router as chat,auth_router,constellation
from app.models.db.login_log import LoginLog
from app.services.chat_service import save_gpt_response as original_save
fixture.Base.metadata.create_all(fixture.engine)
app=fixture.app
for router in (chat.router,auth_router.router,constellation.router):app.include_router(router)
app.dependency_overrides[auth_router.get_db]=fixture.isolated_db
mode=['success']
release=asyncio.Event()
counts={'upper_reads':0,'garden_loads':0,'logout':0,'chat':0}
@app.middleware('http')
async def observe(request,call_next):
    path=request.url.path
    if path.startswith('/personality-report/'):counts['upper_reads']+=1
    if '/garden/' in path and ('templates' in path or '/js/' in path):counts['garden_loads']+=1
    if path=='/logout':counts['logout']+=1
    if path=='/chat/response_stream':counts['chat']+=1
    return await call_next(request)
@app.post('/test/chat-mode/{kind}')
def set_mode(kind:str):
    release.clear()
    mode[0]=kind
    return {'mode':kind}
@app.post('/test/stream-release')
async def release_stream():
    release.set()
    return {'released':True}
@app.get('/test/legacy-app',response_class=HTMLResponse)
def legacy_app():
    return fixture.actual_app().replace('/static/js/mypage_edit.js?v=20261030-stream1','/test/legacy-loader.js')
@app.get('/test/legacy-loader.js')
def legacy_loader():
    source=(fixture.ROOT/'static/js/mypage_edit.js').read_text(encoding='utf-8')
    return Response(source.replace('/static/js/components/chatting/section.js?v=20261030-stream1','/test/legacy-chat.js'),media_type='text/javascript')
@app.get('/test/legacy-chat.js')
def legacy_chat():
    source=subprocess.check_output(['git','show','3d99c26:static/js/components/chatting/section.js'],cwd=fixture.ROOT)
    return Response(source,media_type='text/javascript')
@app.get('/test/bundle5')
def fixture5():return FileResponse(Path(__file__).with_name('bundle5.html'))
@app.get('/test/bundle5-observed')
def observed():return counts.copy()
async def stream(_):
    yield '합성 답변입니다.\n'
    if mode[0].startswith('gated_'):
        await release.wait()
        if mode[0]=='gated_failure':raise RuntimeError('synthetic')
    if mode[0]=='generation_failure':raise RuntimeError('synthetic')
    yield '화면과 저장을 함께 확인합니다.'
def save(*args,**kwargs):
    if mode[0]=='save_failure':raise RuntimeError('synthetic')
    return original_save(*args,**kwargs)
if __name__=='__main__':
    fixture.seed('ready')
    with fixture.Sessions() as db:
        db.add(LoginLog(user_id=1,login_time=fixture.clock[0]));db.commit()
    with patch.object(fixture.state,'get_kst_now',side_effect=lambda:fixture.clock[0]),patch.object(fixture.study,'get_kst_now',side_effect=lambda:fixture.clock[0]),patch.object(fixture.study.redis,'Redis',return_value=Mock()),patch.object(chat,'stream_gpt_response',stream),patch.object(chat,'build_chat_prompt',return_value=[]),patch.object(chat,'save_gpt_response',save),patch.object(chat,'DiaryService') as diary:
        diary.return_value.check_diary_conditions=AsyncMock(return_value={'available':False})
        fixture.uvicorn.run(app,host='127.0.0.1',port=8012,log_level='warning')
