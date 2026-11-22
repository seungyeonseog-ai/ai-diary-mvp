"""격리 SQLite + 실제 라우터 검사. 외부 AI/원본 사용자 DB에는 접근하지 않는다."""
import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "writing-test-only-secret"
os.environ["OPENAI_API_KEY"] = "test-only-no-network"

import asyncio
import json
import struct
import zlib
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.connection import Base, get_db
from app.api.dependencies.auth_dependencies import get_current_user
from app.api.routers import writing_router as api
from app.models.db.user_model import User
from app.models.db.study_model import DiaryReport
from app.models.db.chat_message_model import ChatMessage
from app.models.db.writing_model import WritingOperation, SummaryRange
from app.services import writing_service as service
from app.services import posthog_capture
from app.core.writing_migration import migrate_writing_schema, require_writing_schema
from tools.migrate_writing import original_digest, migrate

def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind+data))


# 사용자 이미지와 무관한 업로드 검사 전용 1픽셀 PNG 바이트.
PNG = (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB",1,1,8,2,0,0,0))
       + png_chunk(b"IDAT", zlib.compress(b"\x00\xff\x80\x00")) + png_chunk(b"IEND",b""))


class WritingFlowTests(unittest.TestCase):
    def test_state_opportunities_and_prompt_snapshot(self):
        from uuid import uuid4
        writing = self.start()
        self.message(writing)
        self.generate(writing)
        op = self.client.get(f'/writing/{writing}').json()['operations'][0]
        self.assertEqual(op['quota_kind'], 'base')
        with patch.object(api, 'capture_writing_event') as capture:
            path = f'/writing/{writing}/analytics/extra-opportunity'
            self.assertEqual(self.client.post(path).status_code, 204)  # 구형 본문 없는 요청도 호환
            first = [c for c in capture.call_args_list if c.args[0] == 'extra_reply_opportunity'][-1]
            self.assertEqual(first.kwargs['diary_state'], 'none')
            prompt = dict(event='diary_prompt_shown', writing_id=writing, operation_id=op['id'],
                          navigation_id=str(uuid4()), visit_id=str(uuid4()))
            self.assertEqual(self.client.post('/writing/analytics/view', json=prompt).status_code, 204)
            self.assertEqual(capture.call_args.kwargs['extra_remaining'], 2)
            self.assertTrue(capture.call_args.kwargs['extra_allowed'])
            self.assertEqual(capture.call_args.kwargs['diary_state'], 'none')
            diary = self.generate(writing, 'diary', 'd1')['result']['diary_id']
            self.assertEqual(self.client.post(f'/writing/diaries/{diary}/save',json={'version':1}).status_code,200)
            self.assertEqual(self.client.post(path).status_code,204)
            second = [c for c in capture.call_args_list if c.args[0] == 'extra_reply_opportunity'][-1]
            self.assertEqual(second.kwargs['diary_state'],'saved')
            self.assertNotEqual(first.args[2],second.args[2])
            self.owner=2
            self.assertEqual(self.client.post(path).status_code,404)
            self.assertEqual(self.client.post('/writing/analytics/view',json=prompt).status_code,404)

    def test_prompt_window_validation_and_stable_dedup_keys(self):
        from uuid import uuid4
        writing=self.start();self.message(writing);self.generate(writing)
        op=self.client.get(f'/writing/{writing}').json()['operations'][0]
        payload=dict(operation_id=op['id'],attempt_id=str(uuid4()),elapsed_ms=12,diary_state='none')
        path=f'/writing/{writing}/analytics/reply'
        with patch.object(api,'capture_writing_event') as capture:
            self.assertEqual(self.client.post(path,json={**payload,'event':'diary_prompt_window_started'}).status_code,204)
            for _ in range(2):
                self.assertEqual(self.client.post(path,json={**payload,'event':'diary_prompt_window_ended','outcome':'navigate'}).status_code,204)
            self.assertEqual(capture.call_args_list[-1].args[2],capture.call_args_list[-2].args[2])
            self.assertEqual(self.client.post(path,json={**payload,'event':'diary_prompt_window_ended'}).status_code,422)
            self.assertEqual(self.client.post(path,json={**payload,'event':'diary_prompt_window_started','outcome':'navigate'}).status_code,422)
            self.assertEqual(self.client.post(path,json={**payload,'event':'diary_prompt_window_started','diary_state':'saved'}).status_code,409)
            self.owner=2
            self.assertEqual(self.client.post(path,json={**payload,'event':'diary_prompt_window_started'}).status_code,404)

    def test_diary_request_recorded_even_on_generation_failure(self):
        from threading import Event
        writing=self.start();self.message(writing);self.generate(writing)
        sent=Event();events=[]
        def capture(name,*args,**kwargs):
            if name=='diary_generation_requested':events.append((args,kwargs));sent.set()
        with patch.object(api,'capture_writing_event',side_effect=capture):
            self.ai.side_effect=RuntimeError('synthetic failure')
            self.generate(writing,'diary','d-failure',status=503)
            self.assertTrue(sent.wait(3))
        self.assertEqual(len(events),1)
        self.assertEqual(events[0][1]['writing_id'],writing)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite:///" + str(Path(self.temp.name)/"test.db"),
                                    connect_args={"check_same_thread": False, "timeout": 10})
        Base.metadata.create_all(self.engine)
        self.now = datetime(2026, 11, 2, 12)
        self.owner = 1
        with Session(self.engine) as db:
            db.add_all([User(id=i, username=f"synthetic{i}", email=f"synthetic{i}@example.org",
                             nickname="합성", hashed_password="unused", registered_at=self.now) for i in (1, 2)])
            db.commit()
        self.clock = patch.object(service, "get_kst_now", side_effect=lambda: self.now).start()
        patch.object(api, "get_kst_now", side_effect=lambda: self.now).start()
        async def fake_generate(kind, source):
            return {"title": "합성 제목", "body": source} if kind == "diary" else {"bubbles": ["마음이 쓰였겠어.", "애썼어."]}
        self.ai = AsyncMock(side_effect=fake_generate)
        patch.object(api, "generate", self.ai).start()
        app = FastAPI()
        app.include_router(api.router)
        def isolated_db():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = isolated_db
        app.dependency_overrides[get_current_user] = lambda: User(id=self.owner)
        self.app, self.client = app, TestClient(app)

    def tearDown(self):
        patch.stopall()
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def start(self):
        response = self.client.post("/writing")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def test_message_snapshot_roundtrip_retry_and_account_isolation(self):
        writing = self.start()
        path = f"/writing/{writing}/messages?include_state=true"
        payload = {"request_id": "snapshot-message", "message": "합성 전송 내용"}
        first = self.client.post(path, json=payload)
        self.assertEqual(first.status_code, 200)
        snapshot = first.json()["snapshot"]
        self.assertEqual(snapshot["id"], writing)
        self.assertEqual([m["message"] for m in snapshot["messages"]], [payload["message"]])
        retry = self.client.post(path, json=payload)
        self.assertEqual(retry.json()["id"], first.json()["id"])
        self.assertEqual(len(retry.json()["snapshot"]["messages"]), 1)
        legacy = self.client.post(f"/writing/{writing}/messages", json=payload)
        self.assertNotIn("snapshot", legacy.json())
        self.owner = 2
        self.assertEqual(self.client.post(path, json=payload).status_code, 404)

    def message(self, writing, text="합성 이야기", key="msg1"):
        response = self.client.post(f"/writing/{writing}/messages", json={"request_id": key, "message": text})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def generate(self, writing, kind="lamp", key="lamp1", status=200):
        response = self.client.post(f"/writing/{writing}/generate/{kind}", json={"request_id": key})
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def draft(self):
        writing = self.start()
        self.message(writing)
        self.generate(writing)
        result = self.generate(writing, "diary", "diary1")
        return writing, result["result"]["diary_id"]

    def test_draft_edit_save_same_row_and_retry(self):
        writing, diary_id = self.draft()
        self.assertEqual(self.client.get("/writing/diaries").json()["total"], 0)
        detail = self.client.get(f"/writing/diaries/{diary_id}").json()
        self.assertEqual(detail["state"], "draft")
        edited = self.client.patch(f"/writing/diaries/{diary_id}", json={
            "version": 1, "title": "수정 제목", "body": "수정 본문"})
        self.assertEqual(edited.status_code, 200)
        for _ in range(2):
            response = self.client.post(f"/writing/diaries/{diary_id}/save", json={"version": 2})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["version"], 3)
        self.assertEqual(self.client.get("/writing/diaries").json()["total"], 1)
        self.assertEqual(self.client.get(f"/writing/{writing}").json()["diary"]["body"], "수정 본문")
        with Session(self.engine) as db:
            self.assertEqual(db.query(DiaryReport).count(), 1)

    def test_first_save_captures_once_after_commit_and_survives_delivery_failure(self):
        _, diary_id = self.draft()
        path = f"/writing/diaries/{diary_id}/save"
        settings = {"POSTHOG_ENVIRONMENT": "validation", "POSTHOG_ID_KEY": "test-key",
                    "POSTHOG_HOST": "https://us.i.posthog.com", "POSTHOG_PROJECT_TOKEN": "test-token"}

        def fail_delivery(request, timeout):
            with Session(self.engine) as db:
                self.assertEqual(db.get(DiaryReport, diary_id).state, "saved")
            self.assertEqual(timeout, 3)
            self.assertEqual(request.full_url, "https://us.i.posthog.com/i/v0/e/")
            payload = json.loads(request.data)
            self.assertEqual(payload["event"], "diary_first_saved")
            self.assertNotIn("합성", json.dumps(payload, ensure_ascii=False))
            properties = payload["properties"]
            self.assertEqual(properties["account_kind"], "test")
            self.assertEqual(properties["usage_context"], "internal_test")
            self.assertRegex(properties["distinct_id"], r"^[a-f0-9]{64}$")
            self.assertRegex(properties["diary_id"], r"^[a-f0-9]{64}$")
            self.assertFalse(properties["has_photo"])
            self.assertEqual(properties["edit_kind"], "none")
            raise TimeoutError

        with patch.dict(os.environ, settings), patch.object(posthog_capture, "urlopen", side_effect=fail_delivery) as send:
            self.owner = 2
            self.assertEqual(self.client.post(path, json={"version": 1}).status_code, 404)
            self.owner = 1
            self.assertEqual(self.client.post(path, json={"version": 99}).status_code, 409)
            send.assert_not_called()
            with self.assertLogs(posthog_capture.logger, level="WARNING"):
                self.assertEqual(self.client.post(path, json={"version": 1}).status_code, 200)
            self.assertEqual(self.client.post(path, json={"version": 1}).status_code, 200)
            send.assert_called_once()

    def test_h1_event_creation_before_transport(self):
        with patch.object(api, "capture_writing_event") as record, patch.object(api, "capture_first_save") as saved:
            writing, diary_id = self.draft()
            self.message(writing)
            self.generate(writing, "lamp", "lamp1")
            replay = self.generate(writing, "diary", "diary1")
            self.assertEqual(replay["result"], {"diary_id": diary_id})
            self.assertEqual([call.args[0] for call in record.call_args_list if call.args[0]!='diary_generation_requested'],
                             ["story_started", "reply_completed", "diary_draft_created"])
            view = {"event": "diary_draft_displayed", "diary_id": diary_id}
            self.owner = 2
            self.assertEqual(self.client.post("/writing/analytics/view", json=view).status_code, 404)
            self.owner = 1
            self.assertEqual(self.client.post("/writing/analytics/view", json=view).status_code, 204)
            detail = self.client.get(f"/writing/diaries/{diary_id}").json()
            self.assertEqual(self.client.patch(f"/writing/diaries/{diary_id}", json={
                "version": 1, "title": "변경", "body": detail["body"],
            }).status_code, 200)
            for _ in range(2):
                self.assertEqual(self.client.post(f"/writing/diaries/{diary_id}/save",
                                                  json={"version": 2}).status_code, 200)
            saved.assert_called_once()
            self.assertEqual(saved.call_args.args[-1], "title")
            self.client.delete(f"/writing/diaries/{diary_id}")
            self.assertEqual(record.call_args.args[0], "diary_draft_displayed")

    def test_h1_photo_only_body_both_and_discard(self):
        for kind in ("none", "body", "both", "discard"):
            with self.subTest(kind=kind), patch.object(api, "capture_first_save") as saved, patch.object(
                    api, "capture_writing_event") as record:
                self.now += timedelta(days=1)
                writing = self.start()
                self.message(writing)
                self.generate(writing, key=f"reply-{kind}")
                diary = self.generate(writing, "diary", f"draft-{kind}")["result"]["diary_id"]
                path = f"/writing/diaries/{diary}"
                if kind == "discard":
                    for _ in range(2):
                        self.assertEqual(self.client.delete(f"/writing/{writing}").status_code, 200)
                    self.assertEqual(sum(call.args[0] == "diary_draft_discarded" for call in record.call_args_list), 1)
                    saved.assert_not_called()
                    continue
                detail = self.client.get(path).json()
                if kind == "none":
                    self.assertEqual(self.client.post(path + "/photos?version=1&request_id=photo",
                        content=PNG, headers={"Content-Type": "image/png"}).status_code, 200)
                else:
                    self.assertEqual(self.client.patch(path, json={"version": 1,
                        "title": "변경" if kind == "both" else detail["title"], "body": "본문 변경"}).status_code, 200)
                self.assertEqual(self.client.post(path + "/save", json={"version": 2}).status_code, 200)
                self.assertEqual(saved.call_args.args[-2:], (kind == "none", kind))

    def test_h1_mock_transport_links_generation_save_and_library_views(self):
        from uuid import uuid4
        settings = {"POSTHOG_ENVIRONMENT": "validation", "POSTHOG_ID_KEY": "test-key",
                    "POSTHOG_HOST": "https://us.i.posthog.com", "POSTHOG_PROJECT_TOKEN": "test-token"}
        with patch.dict(os.environ, settings), patch.object(posthog_capture, "urlopen") as transport:
            writing, diary = self.draft()
            self.generate(writing, "diary", "diary1")
            for _ in range(2):
                self.assertEqual(self.client.post(f"/writing/diaries/{diary}/save",
                                                  json={"version": 1}).status_code, 200)
            visit, navigation = str(uuid4()), str(uuid4())
            for view in (
                {"event": "library_entered", "visit_id": visit},
                {"event": "library_entered_after_save", "visit_id": visit, "diary_id": diary},
                {"event": "saved_diary_selected", "visit_id": visit, "navigation_id": navigation, "diary_id": diary},
                {"event": "saved_diary_displayed", "visit_id": visit, "navigation_id": navigation, "diary_id": diary},
                {"event": "saved_diary_edit_opened", "visit_id": visit, "navigation_id": navigation, "diary_id": diary},
            ):
                self.assertEqual(self.client.post("/writing/analytics/view", json=view).status_code, 204)
        events = [json.loads(call.args[0].data) for call in transport.call_args_list]
        requested = [event for event in events if event['event']=='diary_generation_requested']
        self.assertEqual(len(requested),1)
        events = [event for event in events if event['event']!='diary_generation_requested']
        self.assertEqual([event["event"] for event in events], [
            "story_started", "reply_completed", "diary_draft_created", "diary_first_saved",
            "library_entered", "library_entered_after_save", "saved_diary_selected", "saved_diary_displayed",
            "saved_diary_edit_opened",
        ])
        story, reply, draft, save, library, arrival, selected, displayed, edit = (event["properties"] for event in events)
        self.assertEqual(len({props["writing_id"] for props in (story, reply, draft, save)}), 1)
        self.assertEqual(len({props["diary_id"] for props in (draft, save, arrival, selected, displayed)}), 1)
        self.assertEqual(len({props["visit_id"] for props in (library, arrival, selected, displayed)}), 1)
        self.assertEqual(selected["navigation_id"], displayed["navigation_id"])
        for field in ("diary_id", "writing_id", "navigation_id", "visit_id"):
            self.assertEqual(displayed[field], edit[field])
        self.assertEqual(save["edit_kind"], "none")
        self.assertNotIn("합성", json.dumps(events, ensure_ascii=False))

    def test_saved_edit_event_requires_owned_saved_diary_and_library_context(self):
        from uuid import uuid4
        _, diary = self.draft()
        view = {"event": "saved_diary_edit_opened", "diary_id": diary,
                "visit_id": str(uuid4()), "navigation_id": str(uuid4())}
        url = "/writing/analytics/view"
        with patch.object(api, "capture_writing_event") as capture:
            self.assertEqual(self.client.post(url, json=view).status_code, 409)
            self.client.post(f"/writing/diaries/{diary}/save", json={"version": 1})
            for missing in ("visit_id", "navigation_id", "diary_id"):
                self.assertEqual(self.client.post(url, json={k:v for k,v in view.items() if k != missing}).status_code, 422)
            self.owner = 2
            self.assertEqual(self.client.post(url, json=view).status_code, 404)
            self.owner = 1
            self.assertEqual(self.client.post(url, json={**view, "body": "not allowed"}).status_code, 422)
            capture.assert_not_called()
            self.assertEqual(self.client.post(url, json=view).status_code, 204)
            capture.assert_called_once()
            self.assertEqual(self.client.delete(f"/writing/diaries/{diary}").status_code, 200)
            self.assertEqual(self.client.post(url, json=view).status_code, 409)
            capture.assert_called_once()

    def test_discard_arrival_links_only_to_the_new_owned_writing(self):
        from uuid import uuid4
        settings = {"POSTHOG_ENVIRONMENT": "validation", "POSTHOG_ID_KEY": "test-key",
                    "POSTHOG_HOST": "https://us.i.posthog.com", "POSTHOG_PROJECT_TOKEN": "test-token"}
        with patch.dict(os.environ, settings), patch.object(posthog_capture, "urlopen") as transport:
            first, diary = self.draft()
            self.assertEqual(self.client.delete(f"/writing/diaries/{diary}").status_code, 200)
            self.now += timedelta(seconds=1)
            second = self.start()
            url = "/writing/analytics/view"
            arrival = {"event": "space_entered_after_discard", "diary_id": diary, "visit_id": str(uuid4())}
            self.assertEqual(self.client.post(url, json={**arrival, "writing_id": first}).status_code, 409)
            self.owner = 2
            foreign = self.start()
            self.assertEqual(self.client.post(url, json=arrival).status_code, 404)
            self.owner = 1
            self.assertEqual(self.client.post(url, json={**arrival, "writing_id": foreign}).status_code, 404)
            self.assertEqual(self.client.post(url, json={**arrival, "writing_id": second}).status_code, 204)
            self.message(second)
        events = [json.loads(call.args[0].data) for call in transport.call_args_list]
        discard, arrived, story = events[-3:]
        self.assertEqual([event["event"] for event in (discard, arrived, story)],
                         ["diary_draft_discarded", "space_entered_after_discard", "story_started"])
        self.assertEqual(discard["properties"]["diary_id"], arrived["properties"]["diary_id"])
        self.assertEqual(arrived["properties"]["writing_id"], story["properties"]["writing_id"])
        self.assertNotEqual(discard["properties"]["writing_id"], story["properties"]["writing_id"])

    def test_discard_a_new_b_diary_only_b_day_source_a_and_b(self):
        first, diary_id = self.draft()
        self.client.delete(f"/writing/diaries/{diary_id}")
        self.assertEqual(self.client.get(f"/writing/{first}").json()["messages"], [])
        self.now += timedelta(seconds=1)
        second = self.start()
        self.assertNotEqual(first, second)
        self.message(second, "새 작성 B")
        self.generate(second, key="lampB")
        self.generate(second, "diary", "diaryB")
        diary_source = self.ai.call_args.args[1]
        self.assertEqual(diary_source, "USER1. 새 작성 B")
        with Session(self.engine) as db:
            sources = service.day_messages(db, 1, "2026-11-02")
            self.assertEqual([s.message for s in sources], ["합성 이야기", "새 작성 B"])
            self.assertEqual(db.query(ChatMessage).filter_by(role="gpt").count(), 4)
        self.assertEqual(self.client.get(f"/writing/diaries/{diary_id}").status_code, 404)

    def test_bubbles_order_and_no_assistant_in_diary_source(self):
        writing = self.start()
        self.message(writing, "첫째", "m1")
        self.message(writing, "둘째", "m2")
        self.generate(writing)
        self.assertEqual(self.ai.call_args.args, ("lamp", "USER1. 첫째\nUSER2. 둘째"))
        self.generate(writing, "diary", "d1")
        self.assertEqual(self.ai.call_args.args, ("diary", "USER1. 첫째\nUSER2. 둘째"))
        messages = self.client.get(f"/writing/{writing}").json()["messages"]
        self.assertEqual([m["role"] for m in messages], ["user", "user", "gpt", "gpt"])

    def test_duplicate_message_and_request_do_not_duplicate_or_charge(self):
        writing = self.start()
        one = self.message(writing)
        self.assertEqual(one, self.message(writing))
        first = self.generate(writing)
        second = self.generate(writing)
        self.assertEqual(first, second)
        self.assertEqual(self.ai.call_count, 1)
        self.generate(writing, key="new-key-no-new-input", status=409)
        with Session(self.engine) as db:
            self.assertEqual(db.query(WritingOperation).count(), 1)

    def test_extra_two_daily_discard_restores_only_base(self):
        writing = self.start()
        for i in range(3):
            self.message(writing, key=f"m{i}")
            self.generate(writing, key=f"op{i}")
        self.message(writing, key="m3")
        self.generate(writing, key="op3", status=409)
        self.client.delete(f"/writing/{writing}")
        new = self.start()
        state = self.client.get(f"/writing/{new}").json()["quota"]
        self.assertEqual((state["base_remaining"], state["extra_remaining"]), (1, 0))
        self.message(new)
        self.generate(new, key="base-new")
        self.message(new, key="extra-denied")
        self.generate(new, key="extra-new", status=409)
        self.now += timedelta(days=1)
        tomorrow = self.start()
        state = self.client.get(f"/writing/{tomorrow}").json()["quota"]
        self.assertEqual(state["extra_remaining"], 2)

    def test_expiry_exact_seven_days_and_base_survives(self):
        self.now += timedelta(days=7)
        writing = self.start()
        self.message(writing)
        self.generate(writing)
        self.message(writing, key="extra")
        self.generate(writing, key="extra", status=409)
        self.assertEqual(self.client.get(f"/writing/{writing}").json()["quota"]["trial_state"], "expired")

    def test_failure_retry_same_id_preserves_source_and_quota(self):
        writing = self.start()
        self.message(writing)
        self.ai.side_effect = RuntimeError("synthetic outage")
        self.generate(writing, status=503)
        self.ai.side_effect = None
        self.ai.return_value = {"bubbles": ["합성 응답"]}
        self.generate(writing)
        with Session(self.engine) as db:
            self.assertEqual(db.query(WritingOperation).count(), 1)
            self.assertEqual(db.query(ChatMessage).filter_by(role="user").count(), 1)

    def test_after_draft_and_save_extra_dialogue_keeps_diary_and_daily_usage(self):
        writing, diary_id = self.draft()
        original = self.client.get(f"/writing/diaries/{diary_id}").json()
        self.message(writing,"초안 후 이야기","after-draft")
        self.generate(writing,key="after-draft")
        self.client.post(f"/writing/diaries/{diary_id}/save",json={"version":1})
        self.message(writing,"저장 후 이야기","after-save")
        self.generate(writing,key="after-save")
        detail = self.client.get(f"/writing/diaries/{diary_id}").json()
        self.assertEqual((detail["title"],detail["body"]),(original["title"],original["body"]))
        self.assertEqual(detail["state"],"saved")
        quota = self.client.get(f"/writing/{writing}").json()["quota"]
        self.assertEqual((quota["base_remaining"],quota["extra_used"],quota["extra_remaining"]),(0,2,0))
        self.assertEqual(self.client.post(f"/writing/{writing}/messages",json={"request_id":"denied","message":"추가"}).status_code,409)
        self.client.delete(f"/writing/diaries/{diary_id}")
        self.now += timedelta(seconds=1)
        new = self.start()
        quota = self.client.get(f"/writing/{new}").json()["quota"]
        self.assertEqual((quota["base_remaining"],quota["extra_used"],quota["extra_remaining"]),(1,2,0))

    def test_failed_extra_is_not_charged_and_retry_is_charged_once(self):
        writing = self.start();self.message(writing);self.generate(writing)
        self.message(writing,key="extra-message")
        self.ai.side_effect = RuntimeError("synthetic outage")
        self.generate(writing,key="retry-extra",status=503)
        quota = self.client.get(f"/writing/{writing}").json()["quota"]
        self.assertEqual((quota["extra_used"],quota["extra_remaining"]),(0,2))
        self.ai.side_effect = None;self.ai.return_value = {"bubbles":["합성 답변"]}
        self.generate(writing,key="retry-extra");self.generate(writing,key="retry-extra")
        quota = self.client.get(f"/writing/{writing}").json()["quota"]
        self.assertEqual((quota["extra_used"],quota["extra_remaining"]),(1,1))

    def test_start_with_snapshot_matches_read_and_preserves_old_contract(self):
        old = self.client.post('/writing').json()
        self.assertEqual(set(old), {'id', 'date', 'state'})
        self.message(old['id'])
        new = self.client.post('/writing?include_state=true').json()
        self.assertEqual(new['id'], old['id'])
        self.assertEqual(new['snapshot'], self.client.get('/writing/'+old['id']).json())
        self.assertTrue(new['snapshot']['messages'])

    def test_extra_pending_reservation_expiry_and_retry_rechecks_rights(self):
        self.now = datetime(2026,11,6,23,59,50)
        writing = self.start();self.message(writing);self.generate(writing)
        self.message(writing,key="extra")
        op,_ = service.claim_operation(self.engine,1,writing,"boundary","lamp")
        quota = self.client.get(f"/writing/{writing}").json()["quota"]
        self.assertEqual((quota["extra_used"],quota["extra_reserved"],quota["extra_remaining"]),(0,1,1))
        # 가입11/02의 체험 종료는11/07자정. AI 처리 도중 만료면 차감하지 않는다.
        self.now = datetime(2026,11,7)
        with self.assertRaises(service.WritingError):
            service.complete_operation(self.engine,1,op.id,op.lease_token,{"bubbles":["늦은 합성"]})
        service.fail_operation(self.engine,1,op.id,op.lease_token)
        with Session(self.engine) as db:
            self.assertEqual(db.query(WritingOperation).filter_by(quota_kind="extra",state="succeeded").count(),0)

    def test_free_discard_repeatedly_restores_base_and_preserves_sources(self):
        self.now = datetime(2026,11,10,12)
        for index in range(3):
            writing = self.start();self.message(writing,key=f"msg{index}")
            self.generate(writing,key=f"lamp{index}")
            self.client.delete(f"/writing/{writing}")
            self.now += timedelta(seconds=1)
        with Session(self.engine) as db:
            self.assertEqual(len(service.day_messages(db,1,"2026-11-10")),3)
        state = self.client.get(f"/writing/{self.start()}").json()["quota"]
        self.assertEqual((state["base_remaining"],state["extra_remaining"]),(1,0))

    def test_failed_diary_keeps_source_fixed_until_retry(self):
        writing=self.start();self.message(writing);self.generate(writing)
        self.ai.side_effect=RuntimeError("synthetic diary failure")
        self.generate(writing,"diary","d1",status=503)
        response=self.client.post(f"/writing/{writing}/messages",json={"request_id":"late","message":"추가 입력"})
        self.assertEqual(response.status_code,409)
        restored=self.client.get(f"/writing/{writing}").json()
        self.assertTrue(restored["server_now"].endswith("+09:00"))
        with Session(self.engine) as db:self.assertEqual(db.query(ChatMessage).filter_by(role="user").count(),1)

    def test_pending_operation_and_expired_lease(self):
        writing = self.start()
        self.message(writing)
        op, source = service.claim_operation(self.engine, 1, writing, "lease", "lamp")
        self.generate(writing, key="lease", status=409)
        self.generate(writing, key="another", status=409)
        self.now += timedelta(minutes=6)
        retried, source2 = service.claim_operation(self.engine, 1, writing, "lease", "lamp")
        self.assertEqual(source, source2)
        self.assertNotEqual(op.lease_token, retried.lease_token)
        with self.assertRaises(service.WritingError):
            service.complete_operation(self.engine, 1, op.id, op.lease_token, {"bubbles": ["late"]})

    def test_reload_recovers_request_id_without_exposing_lease_token(self):
        writing = self.start()
        self.message(writing)
        op, _ = service.claim_operation(self.engine, 1, writing, "recover-request", "lamp")
        recovered = self.client.get(f"/writing/{writing}").json()
        self.assertEqual(recovered["operations"][0]["request_id"], "recover-request")
        self.assertNotIn(op.lease_token, str(recovered))

    def test_failed_operation_retry_waits_for_other_active_request(self):
        writing = self.start()
        self.message(writing)
        first, _ = service.claim_operation(self.engine,1,writing,"first","lamp")
        service.fail_operation(self.engine,1,first.id,first.lease_token)
        self.message(writing,key="new-message")
        service.claim_operation(self.engine,1,writing,"second","lamp")
        self.generate(writing,key="first",status=409)

    def test_month_validation_and_legacy_saved_only(self):
        from app.repositories.today_chat_message_repository import TodayChatMessageRepository
        writing, diary_id = self.draft()
        from contextlib import contextmanager
        def isolated():
            with Session(self.engine) as db:
                yield db
        with patch("app.repositories.today_chat_message_repository.get_db", isolated):
            repo = TodayChatMessageRepository()
            self.assertEqual(repo.get_user_diaries(1), [])
            self.assertIsNone(repo.get_diary_by_id(diary_id,1))
            self.client.post(f"/writing/diaries/{diary_id}/save",json={"version":1})
            self.assertEqual(len(repo.get_user_diaries(1)),1)
            self.client.delete(f"/writing/{writing}")
            self.assertEqual(repo.get_user_diaries(1), [])
        self.assertEqual(self.client.get('/writing/diaries?month=0000-01').status_code,422)
        self.assertEqual(self.client.get('/writing/diaries?month=9999-12').status_code,422)

    def test_generated_result_save_retry_does_not_call_ai_again(self):
        writing = self.start()
        self.message(writing)
        self.generate(writing)
        with patch.object(service, "complete_operation", side_effect=RuntimeError("synthetic save outage")):
            self.generate(writing, "diary", "d1", status=503)
        calls = self.ai.call_count
        result = self.generate(writing, "diary", "d1")
        self.assertEqual(self.ai.call_count, calls)
        diary_id = result["result"]["diary_id"]
        self.assertEqual(self.client.get(f"/writing/diaries/{diary_id}").json()["state"], "draft")

    def test_photos_three_limit_retry_owner_and_discard(self):
        writing, diary_id = self.draft()
        photo_ids = []
        for i in range(3):
            url = f"/writing/diaries/{diary_id}/photos?version={i+1}&request_id=p{i}"
            response = self.client.post(url, content=PNG)
            self.assertEqual(response.status_code, 200, response.text)
            photo_ids.append(response.json()["id"])
            self.assertEqual(self.client.post(url, content=PNG).json()["id"], photo_ids[-1])
        self.assertEqual(self.client.post(f"/writing/diaries/{diary_id}/photos?version=4&request_id=p4", content=PNG).status_code, 409)
        self.assertEqual(len(self.client.get(f"/writing/diaries/{diary_id}").json()["photos"]), 3)
        url = f"/writing/diaries/{diary_id}/photos/{photo_ids[0]}"
        response = self.client.get(url)
        self.assertEqual(response.content, PNG)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.owner = 2
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(f"/writing/diaries/{diary_id}/photos?version=4&request_id=foreign",content=PNG).status_code,404)
        self.assertEqual(self.client.request("DELETE",url,json={"version":4}).status_code,404)
        self.owner = 1
        self.client.delete(f"/writing/{writing}")
        self.assertEqual(self.client.get(url).status_code,404)

    def test_photo_failure_keeps_text_and_previous_photo(self):
        _, diary_id = self.draft()
        url = f"/writing/diaries/{diary_id}/photos?version=1&request_id=p1"
        self.assertEqual(self.client.post(url, content=PNG).status_code,200)
        next_url = f"/writing/diaries/{diary_id}/photos?version=2&request_id=p2"
        self.assertEqual(self.client.post(next_url, content=b"<svg>bad</svg>").status_code,415)
        with patch.object(api, "MAX_PHOTO_BYTES", 10):
            self.assertEqual(self.client.post(next_url, content=PNG).status_code,413)
        detail = self.client.get(f"/writing/diaries/{diary_id}").json()
        self.assertEqual(detail["body"], "USER1. 합성 이야기")
        self.assertEqual(len(detail["photos"]),1)
        self.assertEqual(detail["version"],2)

    def test_discard_cancels_inflight_generation(self):
        writing = self.start()
        self.message(writing)
        op, _ = service.claim_operation(self.engine, 1, writing, "race", "lamp")
        self.client.delete(f"/writing/{writing}")
        with self.assertRaises(service.WritingError):
            service.complete_operation(self.engine, 1, op.id, op.lease_token, {"bubbles": ["late"]})
        self.assertEqual(self.client.get(f"/writing/{writing}").json()["messages"], [])

    def test_other_user_and_auth_all_mutations(self):
        writing, diary_id = self.draft()
        self.owner = 2
        requests = [
            ("get", f"/writing/{writing}", None),
            ("post", f"/writing/{writing}/messages", {"request_id":"foreign", "message":"bad"}),
            ("post", f"/writing/{writing}/generate/lamp", {"request_id":"foreign"}),
            ("delete", f"/writing/{writing}", None),
            ("get", f"/writing/diaries/{diary_id}", None),
            ("patch", f"/writing/diaries/{diary_id}", {"version":1,"title":"bad","body":"bad"}),
            ("post", f"/writing/diaries/{diary_id}/save", {"version":1}),
            ("delete", f"/writing/diaries/{diary_id}", None),
        ]
        for method, path, data in requests:
            args = {"json":data} if data else {}
            self.assertEqual(self.client.request(method, path, **args).status_code, 404, path)
        self.assertEqual(self.client.get("/writing/diaries").json()["total"], 0)
        self.app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.client.post("/writing").status_code, 401)
        for method, path, data in requests:
            args = {"json":data} if data else {}
            self.assertEqual(self.client.request(method, path, **args).status_code, 401, path)

    def test_stale_edit_and_forged_source_fields_denied(self):
        writing, diary_id = self.draft()
        body = {"version":1,"title":"합성","body":"내용"}
        self.assertEqual(self.client.patch(f"/writing/diaries/{diary_id}", json=body).status_code, 200)
        self.assertEqual(self.client.patch(f"/writing/diaries/{diary_id}", json=body).status_code, 409)
        self.assertEqual(self.client.post(f"/writing/{writing}/generate/diary", json={
            "request_id":"forged", "source_ids":[99], "user_id":2}).status_code, 422)

    def test_saved_past_diary_edit_discard_but_never_recreate_past(self):
        writing, diary_id = self.draft()
        self.client.post(f"/writing/diaries/{diary_id}/save", json={"version":1})
        self.now += timedelta(days=1)
        self.assertEqual(self.client.patch(f"/writing/diaries/{diary_id}", json={
            "version":2,"title":"과거 수정","body":"과거 본문"}).status_code, 200)
        self.client.delete(f"/writing/diaries/{diary_id}")
        self.assertEqual(self.client.post(f"/writing/{writing}/messages", json={
            "request_id":"past", "message":"past"}).status_code, 409)
        new = self.start()
        self.assertEqual(self.client.get(f"/writing/{new}").json()["date"], "2026-11-03")

    def test_summary_ranges_extra_only_and_midnight_date_boundary(self):
        writing = self.start()
        one = self.message(writing, "A", "a")
        two = self.message(writing, "B", "b")
        service.record_summary(self.engine, 1, "2026-11-02", "encouragement", [one,two], "합성 첫 요약")
        self.now = datetime(2026,11,2,23,59,55)
        three = self.message(writing, "C", "c")
        self.now = datetime(2026,11,3,0,0,5)
        next_writing = self.start()
        four = self.message(next_writing, "D", "d")
        with Session(self.engine) as db:
            self.assertEqual([m.id for m in service.unprocessed_day_messages(db,1,"2026-11-02")], [three])
            self.assertEqual([m.id for m in service.day_messages(db,1,"2026-11-03")], [four])
        service.record_summary(self.engine,1,"2026-11-02","midnight",[three],"합성 추가 요약")
        service.record_summary(self.engine,1,"2026-11-02","midnight",[three],"중복 재시도")
        with Session(self.engine) as db:
            self.assertEqual(service.unprocessed_day_messages(db,1,"2026-11-02"), [])
            self.assertEqual(db.query(SummaryRange).count(), 2)
        with self.assertRaises(service.WritingError):
            service.record_summary(self.engine,1,"2026-11-02","midnight",[four],"다른 날짜")

    def test_no_chat_and_no_extra_summary(self):
        writing = self.start()
        self.generate(writing, status=409)
        with Session(self.engine) as db:
            self.assertEqual(service.unprocessed_day_messages(db,1,"2026-11-02"), [])
        with self.assertRaises(service.WritingError):
            service.record_summary(self.engine,1,"2026-11-02","midnight",[],"가짜")

    def test_concurrent_start_and_submission_single_charge(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            starts = list(pool.map(lambda _:service.start_writing(self.engine,1).id, range(2)))
        self.assertEqual(starts[0], starts[1])
        writing = starts[0]
        self.message(writing)
        def claim(_):
            try:
                return service.claim_operation(self.engine,1,writing,"race","lamp")[0].id
            except service.WritingError as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, range(2)))
        self.assertEqual(sum(v==409 for v in results), 1)
        with Session(self.engine) as db:
            self.assertEqual(db.query(WritingOperation).count(), 1)


class MigrationTests(unittest.TestCase):
    def test_legacy_backup_idempotent_migration_and_original_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"legacy.db"
            with closing(sqlite3.connect(path)) as db:
                db.executescript("""
                CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT, email TEXT, hashed_password TEXT, nickname TEXT);
                CREATE TABLE diary_reports(diary_id INTEGER PRIMARY KEY,user_id INTEGER,content TEXT,source_type TEXT,timestamp DATETIME);
                CREATE TABLE chat_messages(id INTEGER PRIMARY KEY,user_id INTEGER,session_id TEXT,role TEXT,message TEXT,timestamp DATETIME,turn INTEGER);
                INSERT INTO users VALUES(1,'synthetic','synthetic@example.org','unused','합성');
                INSERT INTO diary_reports VALUES(8,1,'합성 과거 일기','ai','2026-10-25 12:00:00');
                INSERT INTO chat_messages VALUES(9,1,'legacy','user','합성 원본','2026-11-02 23:59:55',1);
                """)
                before = original_digest(db)
                db.commit()
            backup = migrate(path)
            engine = create_engine("sqlite:///"+path.as_posix())
            require_writing_schema(engine)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(original_digest(db), before)
                self.assertEqual(db.execute("SELECT state,version,title FROM diary_reports").fetchone(), ("saved",1,""))
                trial = db.execute("SELECT registered_at,trial_started_at FROM users").fetchone()
                self.assertIsNone(trial[0])
                self.assertIsNotNone(trial[1])
            migrate_writing_schema(engine)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("SELECT registered_at,trial_started_at FROM users").fetchone(), trial)
            with closing(sqlite3.connect(backup)) as db:
                self.assertEqual(original_digest(db), before)
                self.assertNotIn("state", [r[1] for r in db.execute("PRAGMA table_info(diary_reports)")])
            engine.dispose()


class AdapterTests(unittest.TestCase):
    def run_adapter(self, kind, text):
        client = Mock()
        client.async_client.with_options.return_value = client.async_client
        client.async_client.close = AsyncMock()
        async def stream(prompt, **options):
            self.assertEqual(options["max_completion_tokens"],1800)
            yield text[:len(text)//2]
            yield text[len(text)//2:]
        client.stream_gpt_response = stream
        with patch("app.clients.gpt_api.GPTClient", return_value=client):
            return asyncio.run(api.generate(kind,"USER1. 합성 자료"))

    def test_title_body_json_across_chunks(self):
        self.assertEqual(self.run_adapter("diary",'{"title":"합성","body":"합성 본문"}'),
                         {"title":"합성","body":"합성 본문"})

    def test_invalid_and_question_output_rejected(self):
        for raw in ('not-json','{"bubbles":[]}','{"bubbles":["어땠어?"]}'):
            with self.assertRaises(ValueError):
                self.run_adapter("lamp",raw)

    def test_truncated_provider_output_is_failure(self):
        from app.clients.gpt_api import GPTClient
        from types import SimpleNamespace
        async def run():
            client = GPTClient()
            async def chunks():
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="partial"),finish_reason=None)])
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None),finish_reason="length")])
            client.async_client.chat.completions.create = AsyncMock(return_value=chunks())
            try:
                async for _ in client.stream_gpt_response("합성",max_completion_tokens=1800):
                    pass
            finally:
                await client.async_client.close()
                client.client.close()
        with self.assertRaises(RuntimeError):
            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
