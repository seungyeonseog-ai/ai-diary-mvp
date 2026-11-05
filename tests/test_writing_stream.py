"""외부 호출 없는 완성 말풍선 스트림/실제 저장/취소·재시도 검사."""
import os
os.environ["DATABASE_URL"]="sqlite:///:memory:"
os.environ["SECRET_KEY"]="stream-test-only-secret"
os.environ["OPENAI_API_KEY"]="test-only-no-network"
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core.connection import Base,get_db
from app.models.db.user_model import User
from app.models.db.chat_message_model import ChatMessage
from app.models.db.writing_model import WritingOperation
from app.api.dependencies.auth_dependencies import get_current_user
from app.api.routers.writing_router import router
from app.api.routers import writing_router
from app.services import posthog_capture
from app.services import writing_service as service, writing_stream as stream


class ParserTests(unittest.TestCase):
    def test_only_complete_strings_with_json_escapes(self):
        # 완성되지 않은 문자열은 표시하지 않는다.
        self.assertEqual(stream.completed_bubbles('{"bubbles":["첫'),[])
        self.assertEqual(stream.completed_bubbles(r'{"bubbles":["\uD55C'),[])
        self.assertEqual(stream.completed_bubbles(r'{"bubbles":["\uD55C"'),['한'])
        first='쉼표, 와 "따옴표"\n줄바꿈'
        raw=json.dumps({'bubbles':[first,'둘째']},ensure_ascii=False)
        self.assertEqual(stream.completed_bubbles(raw),[first,'둘째'])
        self.assertEqual(stream.completed_bubbles(raw[:raw.index('둘째')+1]),[first])

    def test_question_empty_and_nonstring_rejected(self):
        for data in ('{"bubbles":["질문?"]}','{"bubbles":[""]}','{"bubbles":[3]}'):
            with self.assertRaises(ValueError):stream.completed_bubbles(data)


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.engine=create_engine('sqlite:///'+str(Path(self.temp.name)/'stream.db'),connect_args={'check_same_thread':False})
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add_all([User(id=i,username=f'stream{i}',email=f'stream{i}@example.org',nickname='합성',hashed_password='unused') for i in (1,2)])
            db.commit()
        self.writing=service.start_writing(self.engine,1)
        service.add_message(self.engine,1,self.writing.id,'m1','합성 첫 이야기')
        self.memory=patch.object(stream,'memory_context',return_value=[]).start()

    def tearDown(self):
        patch.stopall();self.engine.dispose();self.temp.cleanup()

    def claim(self):return service.claim_operation(self.engine,1,self.writing.id,'lamp1','lamp')
    def run_collect(self,op,source):
        async def collect():return [frame async for frame in stream.response_events(self.engine,1,op,source)]
        return asyncio.run(collect())

    def test_first_bubble_precedes_next_chunk_and_persistence(self):
        async def run():
            gate=asyncio.Event()
            async def chunks(*_):
                yield '{"bubbles":["완성된 첫 답변",'
                await gate.wait()
                yield '"완성된 둘째 답변"]}'
            with patch.object(stream,'lamp_chunks',chunks):
                op,source=self.claim();events=stream.response_events(self.engine,1,op,source)
                first=await anext(events);self.assertIn('event: bubble',first)
                with Session(self.engine) as db:
                    self.assertEqual(db.query(ChatMessage).filter_by(role='gpt').count(),0)
                    self.assertEqual(db.get(WritingOperation,op.id).state,'pending')
                task=asyncio.create_task(anext(events));await asyncio.sleep(0)
                self.assertFalse(task.done())
                gate.set();second=await task;self.assertIn('둘째',second)
                saved=await anext(events);self.assertIn('event: saved',saved)
                await events.aclose()
                with Session(self.engine) as db:
                    self.assertEqual(db.query(ChatMessage).filter_by(role='gpt').count(),2)
        asyncio.run(run())

    def test_checkpoint_save_failure_retry_uses_cached_result(self):
        calls=[]
        async def chunks(*_):calls.append(1);yield '{"bubbles":["합성 답변"]}'
        with patch.object(stream,'lamp_chunks',chunks):
            op,source=self.claim()
            with patch.object(service,'complete_operation',side_effect=RuntimeError('save failed')):
                frames=self.run_collect(op,source)
            self.assertIn('event: error',frames[-1])
            retried,source=self.claim();frames=self.run_collect(retried,source)
            self.assertIn('event: saved',frames[-1]);self.assertEqual(len(calls),1)
            replay,source=self.claim();frames=self.run_collect(replay,source)
            self.assertIn('event: saved',frames[-1]);self.assertEqual(len(calls),1)
            with Session(self.engine) as db:
                self.assertEqual(db.query(WritingOperation).count(),1)
                self.assertEqual(db.query(ChatMessage).filter_by(role='gpt').count(),1)

    def test_cancelled_stream_can_retry_same_request(self):
        async def run():
            async def chunks(*_):yield '{"bubbles":["첫째",';await asyncio.Event().wait()
            with patch.object(stream,'lamp_chunks',chunks):
                op,source=self.claim();events=stream.response_events(self.engine,1,op,source)
                await anext(events);await events.aclose()
                with Session(self.engine) as db:self.assertEqual(db.get(WritingOperation,op.id).state,'failed')
                self.claim()
        asyncio.run(run())

    def test_malformed_final_json_does_not_store_partial_bubble(self):
        async def chunks(*_):yield '{"bubbles":["일부 답변",';yield 'broken}'
        with patch.object(stream,'lamp_chunks',chunks):
            op,source=self.claim();frames=self.run_collect(op,source)
            self.assertIn('event: error',frames[-1])
            with Session(self.engine) as db:
                self.assertEqual(db.query(ChatMessage).filter_by(role='gpt').count(),0)
                self.assertEqual(db.query(ChatMessage).filter_by(role='user').count(),1)

    def test_http_route_owner_and_sse_contract(self):
        app=FastAPI();app.include_router(router)
        def db():
            with Session(self.engine) as session:yield session
        app.dependency_overrides[get_db]=db
        app.dependency_overrides[get_current_user]=lambda:User(id=2)
        async def chunks(*_):yield '{"bubbles":["합성 답변"]}'
        with TestClient(app) as client,patch.object(stream,'lamp_chunks',chunks):
            path=f'/writing/{self.writing.id}/response_stream'
            self.assertEqual(client.post(path,json={'request_id':'lamp1'}).status_code,404)
            app.dependency_overrides[get_current_user]=lambda:User(id=1)
            response=client.post(path,json={'request_id':'lamp1'})
            self.assertEqual(response.status_code,200)
            self.assertIn('text/event-stream',response.headers['content-type'])
            self.assertIn('event: bubble',response.text);self.assertIn('event: saved',response.text)
            app.dependency_overrides.pop(get_current_user)
            self.assertEqual(client.post(path,json={'request_id':'lamp1'}).status_code,401)

    def exercise_extra_analytics(self):
        with Session(self.engine) as db:
            db.get(User, 1).registered_at = service.get_kst_now()
            db.commit()
        app = FastAPI()
        app.include_router(router)
        owner = 1

        def database():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = lambda: User(id=owner)
        root = f"/writing/{self.writing.id}"
        opportunity = root + "/analytics/extra-opportunity"
        op, _ = self.claim()
        with TestClient(app) as client:
            self.assertEqual(client.post(opportunity).status_code, 409)
            service.complete_operation(self.engine, 1, op.id, op.lease_token, {"bubbles": ["합성 기본 답변"]})
            self.assertEqual(client.post(opportunity).status_code, 204)
            service.add_message(self.engine, 1, self.writing.id, "extra-message", "합성 추가 이야기")

            async def bad_chunks(*_):
                yield '{"bubbles":["합성 부분 답변",'

            async def good_chunks(*_):
                yield '{"bubbles":["합성 추가 답변"]}'

            first_attempt, retry_attempt = str(uuid4()), str(uuid4())
            payload = {"request_id": "extra-request"}
            path = root + "/response_stream"
            with patch.object(stream, "lamp_chunks", bad_chunks):
                failed = client.post(path, params={"attempt_id": first_attempt}, json=payload)
                self.assertIn("event: error", failed.text)
            self.assertEqual(client.post(opportunity).status_code, 409)
            with patch.object(stream, "lamp_chunks", good_chunks):
                saved = client.post(path, params={"attempt_id": retry_attempt}, json=payload)
                replay = client.post(path, params={"attempt_id": retry_attempt}, json=payload)
            self.assertIn("event: saved", saved.text)
            self.assertIn("event: saved", replay.text)
            operation = saved.headers["X-Writing-Operation"]
            self.assertEqual(failed.headers["X-Writing-Operation"], operation)
            self.assertNotIn("X-Writing-Operation", replay.headers)
            observation = {"operation_id": operation, "attempt_id": retry_attempt, "elapsed_ms": 10}
            owner = 2
            self.assertEqual(client.post(root + "/analytics/reply",
                json={**observation, "event": "reply_first_displayed"}).status_code, 404)
            owner = 1
            for event, properties in (
                ("reply_first_displayed", {}),
                ("reply_completion_displayed", {"diary_state": "none"}),
                ("reply_followup", {"action": "story_input"}),
            ):
                self.assertEqual(client.post(root + "/analytics/reply",
                    json={**observation, "event": event, **properties}).status_code, 204)
        with Session(self.engine) as db:
            self.assertEqual(db.get(WritingOperation, operation).state, "succeeded")
            self.assertEqual(service.quota(db, 1, self.writing, service.get_kst_now())["extra_used"], 1)

    def test_extra_analytics_events_before_transport(self):
        with patch.object(writing_router, "capture_writing_event") as capture:
            self.exercise_extra_analytics()
        self.assertEqual([call.args[0] for call in capture.call_args_list], [
            "extra_reply_available", "reply_requested", "reply_failed", "reply_requested", "reply_completed",
            "reply_first_displayed", "reply_completion_displayed", "reply_followup",
        ])
        self.assertEqual(capture.call_args_list[4].kwargs["reply_kind"], "extra")
        self.assertEqual(capture.call_args_list[6].kwargs["diary_state"], "none")

    def test_extra_analytics_mock_transport(self):
        settings = {"POSTHOG_ENVIRONMENT": "validation", "POSTHOG_ID_KEY": "test-key",
                    "POSTHOG_HOST": "https://us.i.posthog.com", "POSTHOG_PROJECT_TOKEN": "test-token"}
        with patch.dict(os.environ, settings), patch.object(posthog_capture, "urlopen") as transport:
            self.exercise_extra_analytics()
        events = [json.loads(call.args[0].data) for call in transport.call_args_list]
        self.assertEqual(len(events), 8)
        self.assertEqual(len({event["properties"]["event_id"] for event in events}), 8)
        reply = [event["properties"] for event in events[1:]]
        self.assertEqual(len({props["operation_id"] for props in reply}), 1)
        self.assertEqual(len({props["attempt_id"] for props in reply}), 2)
        self.assertEqual(reply[0]["attempt_id"], reply[1]["attempt_id"])
        self.assertEqual(reply[2]["attempt_id"], reply[3]["attempt_id"])
        self.assertNotIn("합성", json.dumps(events, ensure_ascii=False))

    def test_migrated_account_cannot_bypass_new_flow_via_legacy_creation(self):
        from app.api.routers import chat_message_router,study_router
        app=FastAPI();app.include_router(chat_message_router.router);app.include_router(study_router.router)
        def db():
            with Session(self.engine) as session:yield session
        app.dependency_overrides[get_db]=db
        app.dependency_overrides[get_current_user]=lambda:User(id=1)
        with TestClient(app) as client:
            for path,data in [('/chat/send',{'message':'합성'}),('/chat/response_stream',{'turn':1,'session_id':'own'}),
                              ('/study/diary/generate/stream',{}),('/study/user/diary/save',{'content':'합성'})]:
                self.assertEqual(client.post(path,json=data).status_code,409,path)
            self.assertEqual(client.get('/chat/list').status_code,200)
            app.dependency_overrides[get_current_user]=lambda:User(id=2)
            with patch.object(chat_message_router,'get_or_create_session_id',return_value='legacy-fixture'),patch.object(chat_message_router,'save_user_message',return_value=1):
                self.assertEqual(client.post('/chat/send',json={'message':'합성'}).status_code,200)


if __name__=='__main__':unittest.main()
