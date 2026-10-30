"""M08/M10/M14 실제 라우터·DB·태스크 실패 경로. 외부 AI/Redis 무호출."""
import os
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['SECRET_KEY']='core-isolated'
os.environ['OPENAI_API_KEY']='test-placeholder'
import asyncio,json,unittest,tempfile,threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import Mock,patch,AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.connection import Base,get_db
from app.api.dependencies.auth_dependencies import get_current_user
from app.models.db.user_model import User
from app.models.db.session_log import SessionLog
from app.models.db.session_summary import GPTSessionSummary
from app.models.db.chat_message_model import ChatMessage
from app.models.db.study_model import DiaryReport
from app.api.routers import chat_message_router as chat, study_router as study
from app.services import gpt_session_summary_service as summary
from app.services.manual_diary_service import save_manual_diary,ManualDiaryAlreadyExists
from app.services import celery_app as tasks
from app.clients import gpt_api

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='bundle5-core-')
        self.engine=create_engine('sqlite:///'+(Path(self.temp.name)/'isolated.db').as_posix(),connect_args={'check_same_thread':False,'timeout':10})
        Base.metadata.create_all(self.engine);self.sessions=sessionmaker(bind=self.engine)
        with self.sessions() as db:
            for uid in (1,2):
                db.add(User(id=uid,username=f'u{uid}',email=f'u{uid}@example.test',nickname='tester',hashed_password='unused'))
                db.add(ChatMessage(user_id=uid,session_id=f's{uid}',turn=1,role='user',message='synthetic'))
            db.commit()
        self.uid=1;app=FastAPI();app.include_router(chat.router);app.include_router(study.router)
        def isolated_db():
            with self.sessions() as db:yield db
        app.dependency_overrides[get_db]=isolated_db
        app.dependency_overrides[get_current_user]=lambda:User(id=self.uid)
        self.app=app;self.client=TestClient(app,headers={'Accept':'text/event-stream'})
    def tearDown(self):
        self.client.close();self.engine.dispose();self.temp.cleanup()
    def stream(self,chunks=('합성 ','답변'),failure=False,save_error=False):
        async def synthetic(_):
            for item in chunks:yield item
            if failure:raise RuntimeError('private-upstream')
        with patch.object(chat,'build_chat_prompt',return_value=[]),patch.object(chat,'stream_gpt_response',synthetic),patch.object(chat,'DiaryService') as diary:
            diary.return_value.check_diary_conditions=AsyncMock(return_value={'available':False})
            if save_error:
                with patch.object(chat,'save_gpt_response',side_effect=RuntimeError('private-sql')):
                    response=self.client.post('/chat/response_stream',json={'turn':1,'session_id':'s1'})
            else:response=self.client.post('/chat/response_stream',json={'turn':1,'session_id':'s1'})
        self.assertNotIn('private-',response.text)
        return [(x.splitlines()[0][7:],json.loads(x.splitlines()[1][6:])) for x in response.text.strip().split('\n\n')]
    def assistant_count(self):
        with self.sessions() as db:return db.query(ChatMessage).filter_by(role='assistant').count()
    def test_chat_saves_before_terminal_success(self):
        frames=self.stream();self.assertEqual([x[0] for x in frames],['chunk','chunk','saved'])
        self.assertEqual(self.assistant_count(),1)
    def test_legacy_chat_receives_text_without_sse_frames(self):
        self.client.headers['Accept'] = '*/*'
        async def synthetic(_):
            yield '합성 '
            yield '답변'
        with patch.object(chat,'build_chat_prompt',return_value=[]),patch.object(chat,'stream_gpt_response',synthetic),patch.object(chat,'DiaryService') as diary:
            diary.return_value.check_diary_conditions=AsyncMock(return_value={'available':False})
            response=self.client.post('/chat/response_stream',json={'turn':1,'session_id':'s1'})
        self.assertEqual(response.text,'합성 답변')
        self.assertTrue(response.headers['content-type'].startswith('text/plain'))
        self.assertEqual(response.headers['vary'],'Accept')
        self.assertEqual(self.assistant_count(),1)
    def test_stream_yields_chunks_before_generation_and_save_finish(self):
        from starlette.requests import Request
        from app.models.schemas.chat_schema import ChatResponseInput
        async def run():
            async def synthetic(_):
                yield '첫 청크'
                yield '둘째 청크'
            with self.sessions() as db, patch.object(chat,'build_chat_prompt',return_value=[]),patch.object(chat,'stream_gpt_response',synthetic),patch.object(chat,'save_gpt_response') as save,patch.object(chat,'DiaryService') as diary:
                diary.return_value.check_diary_conditions=AsyncMock(return_value={'available':False})
                request=Request({'type':'http','headers':[(b'accept',b'text/event-stream')]})
                response=await chat.stream_response(ChatResponseInput(turn=1,session_id='s1'),request,db,User(id=1))
                stream=response.body_iterator
                self.assertIn('첫 청크',await anext(stream));save.assert_not_called()
                self.assertIn('둘째 청크',await anext(stream));save.assert_not_called()
                self.assertIn('event: saved',await anext(stream));save.assert_called_once()
                await stream.aclose()
        asyncio.run(run())
    def test_chat_partial_failure_does_not_save(self):
        frames=self.stream(failure=True);self.assertEqual(frames[-1][1]['code'],'generation_failed');self.assertEqual(self.assistant_count(),0)
    def test_chat_empty_response_does_not_save(self):
        self.assertEqual(self.stream(chunks=[])[-1][1]['code'],'generation_failed');self.assertEqual(self.assistant_count(),0)
    def test_chat_save_failure_is_distinct(self):
        self.assertEqual(self.stream(save_error=True)[-1][1]['code'],'save_failed');self.assertEqual(self.assistant_count(),0)
    def test_chat_commit_failure_rolls_back(self):
        from app.services.chat_service import save_gpt_response
        with self.sessions() as db,patch.object(db,'commit',side_effect=RuntimeError('private-sql')):
            with self.assertRaises(RuntimeError):save_gpt_response(db,1,'synthetic',1,'s1')
        self.assertEqual(self.assistant_count(),0)
    def test_chat_cannot_request_foreign_or_absent_turn(self):
        with patch.object(chat,'build_chat_prompt') as prompt:
            for body in ({'turn':1,'session_id':'s2'},{'turn':999,'session_id':'s1'}):
                self.assertEqual(self.client.post('/chat/response_stream',json=body).status_code,404)
            self.assertEqual(self.client.post('/chat/response_stream',json={'turn':0,'session_id':'s1'}).status_code,422)
            prompt.assert_not_called()
    def test_gpt_stream_raises_instead_of_yielding_error_text(self):
        async def run():
            with patch.object(gpt_api.client.chat.completions,'create',side_effect=RuntimeError('private-upstream')):
                with self.assertRaises(RuntimeError):
                    async for _ in gpt_api.stream_gpt_response([]):self.fail('error yielded as answer')
        asyncio.run(run())
    def test_gpt_length_limit_does_not_become_saved_success(self):
        from types import SimpleNamespace as Obj
        async def run():
            chunks=[Obj(choices=[Obj(delta=Obj(content='partial'),finish_reason=None)]),Obj(choices=[Obj(delta=Obj(content=None),finish_reason='length')])]
            with patch.object(gpt_api.client.chat.completions,'create',return_value=chunks):
                with self.assertRaises(RuntimeError):
                    async for _ in gpt_api.stream_gpt_response([]):pass
        asyncio.run(run())
    def test_manual_validation(self):
        for data in ({},{'content':None},{'content':12},{'content':[]},{'content':''},{'content':' \n '},{'content':'a'*50001}):
            self.assertEqual(self.client.post('/study/user/diary/save',json=data).status_code,422)
        with self.sessions() as db:self.assertEqual(db.query(DiaryReport).count(),0)
    def test_manual_owner_and_duplicate_and_ai_independent(self):
        with self.sessions() as db:
            db.add(DiaryReport(user_id=1,source_type='ai',content='synthetic'));db.commit()
        self.assertEqual(self.client.post('/study/user/diary/save',json={'content':'  합성 일기  ','user_id':2,'source_type':'ai'}).status_code,200)
        self.assertEqual(self.client.post('/study/user/diary/save',json={'content':'second'}).status_code,409)
        self.uid=2;self.assertEqual(self.client.post('/study/user/diary/save',json={'content':'other'}).status_code,200)
        with self.sessions() as db:self.assertEqual(db.query(DiaryReport).filter_by(user_id=1,source_type='user').one().content,'합성 일기')
    def test_manual_concurrent_requests_store_one(self):
        barrier=threading.Barrier(2)
        def run(_):
            barrier.wait()
            try:save_manual_diary(self.engine,1,'synthetic');return 'saved'
            except ManualDiaryAlreadyExists:return 'duplicate'
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertCountEqual(pool.map(run,range(2)),['saved','duplicate'])
        with self.sessions() as db:self.assertEqual(db.query(DiaryReport).count(),1)
    def test_manual_kst_day_boundary(self):
        with patch('app.services.manual_diary_service.get_kst_now',return_value=datetime(2026,10,29,23,59,59)):
            save_manual_diary(self.engine,1,'first')
        with patch('app.services.manual_diary_service.get_kst_now',return_value=datetime(2026,10,30,0,0,0)):
            save_manual_diary(self.engine,1,'next')
        with self.sessions() as db:self.assertEqual(db.query(DiaryReport).count(),2)
    def test_manual_commit_failure_no_partial_or_raw_error(self):
        with patch.object(study,'save_manual_diary',side_effect=RuntimeError('private-sql')):
            response=self.client.post('/study/user/diary/save',json={'content':'synthetic'})
            self.assertEqual(response.status_code,500);self.assertNotIn('private-sql',response.text)
        with patch('app.services.manual_diary_service.Session.commit',side_effect=RuntimeError('private-sql')):
            with self.assertRaises(RuntimeError):save_manual_diary(self.engine,1,'synthetic')
        with self.sessions() as db:self.assertEqual(db.query(DiaryReport).count(),0)
    def test_summary_invalid_shapes_never_store(self):
        svc=summary.GPTSessionSummaryService();svc.chat_repo=Mock();svc.chat_repo.today_session_user_chats_formatted.return_value='synthetic'
        for payload in ('bad-json',json.dumps([]),json.dumps({'summary':''}),json.dumps({'summary':'valid','keywords':'bad'}),json.dumps({'summary':'valid','keywords':[12]})):
            with patch.object(summary,'call_gpt',return_value=payload):self.assertIsNone(svc.create_session_summary(1,'s1'))
        with self.sessions() as db:self.assertEqual(db.query(GPTSessionSummary).count(),0)
    def test_summary_success_commits_before_result(self):
        svc=summary.GPTSessionSummaryService();svc.chat_repo=Mock();svc.chat_repo.today_session_user_chats_formatted.return_value='synthetic'
        def db_provider():
            with self.sessions() as db:yield db
        payload={'summary':'synthetic summary','key_sentence':'synthetic','keywords':['test']}
        with patch.object(summary,'call_gpt',return_value=json.dumps(payload)),patch.object(summary,'get_db',db_provider):self.assertEqual(svc.create_session_summary(1,'s1'),payload)
        with self.sessions() as db:self.assertEqual(db.query(GPTSessionSummary).count(),1)
    def test_summary_task_none_never_dispatches_embedding(self):
        with patch.object(summary,'GPTSessionSummaryService') as service,patch.object(tasks.session_embed_task,'delay') as embed:
            service.return_value.create_session_summary.return_value=None
            self.assertEqual(tasks.session_summarize_task.run(1,'s1')['status'],'not_summarized');embed.assert_not_called()
    def test_summary_task_success_dispatches_embedding(self):
        with patch.object(summary,'GPTSessionSummaryService') as service,patch.object(tasks.session_embed_task,'delay') as embed:
            service.return_value.create_session_summary.return_value={'summary':'synthetic'}
            tasks.session_summarize_task.run(1,'s1');embed.assert_called_once_with(user_id=1,session_id='s1')
    def test_summary_task_failure_does_not_dispatch_embedding(self):
        with patch.object(summary,'GPTSessionSummaryService') as service,patch.object(tasks.session_embed_task,'delay') as embed,patch.object(tasks.session_summarize_task,'retry',side_effect=RuntimeError('synthetic-retry')):
            service.return_value.create_session_summary.side_effect=RuntimeError('private-sql')
            with self.assertRaises(RuntimeError):tasks.session_summarize_task.run(1,'s1')
            embed.assert_not_called()
    def test_routes_require_authentication(self):
        self.app.dependency_overrides.pop(get_current_user)
        for url,body in [('/chat/response_stream',{'turn':1,'session_id':'s1'}),('/study/user/diary/save',{'content':'synthetic'})]:
            self.assertEqual(self.client.post(url,json=body).status_code,401)

if __name__=='__main__':unittest.main()
