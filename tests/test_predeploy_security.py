"""외부 AI/Redis 및 사용자 DB를 사용하지 않는 배포 전 회귀 검사."""
import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
import io
import os
import unittest
from unittest.mock import AsyncMock, patch

# 앱 모듈을 가져오기 전에 테스트 설정으로 격리한다.
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-only-secret-do-not-use-outside-tests'
os.environ['OPENAI_API_KEY'] = 'test-placeholder-not-a-real-key'

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.core.connection import Base, get_db
from app.core.token_utils import ALGORITHM, SECRET_KEY, decode_token, encode_token
from app.config.settings import PROJECT_ROOT, Settings
from app.models.db.user_model import User
from app.models.db.study_model import PersonalityReport
from app.models.db.session_log import SessionLog
from app.models.db.chat_message_model import ChatMessage
from app.api.routers import constellation, websocket_router
from app.tasks.session_task_runner import check_and_close_expired_sessions_for_user
from app.utils.time_utils import get_kst_now


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(bind=cls.engine)
        with cls.sessions() as db:
            for uid in (1, 2):
                db.add(User(id=uid, username=f'user{uid}', email=f'u{uid}@example.test', hashed_password='unused', nickname='tester'))
            db.add(PersonalityReport(id=1, user_id=1, query=['private'], report_result={'성향': 'private-owner-content'}, date_str='2026-10-28'))
            db.commit()
        cls.feature_patch = patch.object(constellation.settings, 'upper_reports_enabled', True)
        cls.feature_patch.start()
        cls.app = FastAPI()
        cls.app.include_router(constellation.router)
        cls.app.include_router(websocket_router.router)

        def isolated_db():
            with cls.sessions() as db:
                yield db
        cls.app.dependency_overrides[get_db] = isolated_db
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.feature_patch.stop()
        cls.client.close()
        cls.engine.dispose()

    def headers(self, uid):
        return {'Authorization': f'Bearer {encode_token(uid)}'}

    def test_report_requires_login(self):
        self.assertEqual(self.client.get('/personality-report/1').status_code, 401)

    def test_report_owner_can_read(self):
        response = self.client.get('/personality-report/1', headers=self.headers(1))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['personality_tendency'], 'private-owner-content')

    def test_report_foreign_owner_and_absent_both_404(self):
        for report_id in (1, 999):
            response = self.client.get(f'/personality-report/{report_id}', headers=self.headers(2))
            self.assertEqual(response.status_code, 404)
            self.assertNotIn('private-owner-content', response.text)

    def test_invalid_or_missing_user_token_rejected(self):
        self.assertEqual(self.client.get('/personality-report/1', headers={'Authorization': 'Bearer broken'}).status_code, 401)
        self.assertEqual(self.client.get('/personality-report/1', headers=self.headers(999)).status_code, 401)

    def test_token_expiration_is_utc_and_not_logged(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            token = encode_token(1)
            payload = decode_token(token)
        seconds = payload['exp'] - datetime.now(timezone.utc).timestamp()
        self.assertTrue(1790 < seconds <= 1800)
        self.assertNotIn(token, output.getvalue())
        self.assertNotIn(SECRET_KEY, output.getvalue())

    def test_expired_or_no_expiration_token_rejected(self):
        for payload in ({'user_id': 1}, {'user_id': 1, 'exp': datetime.now(timezone.utc) - timedelta(seconds=1)}):
            token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
            with self.assertRaises(ValueError):
                decode_token(token)

    def assert_socket_rejected(self, uid, auth):
        with patch.object(websocket_router, 'SessionLocal', self.sessions), patch.object(websocket_router.websocket_service, 'connect', new_callable=AsyncMock) as connect:
            with self.client.websocket_connect(f'/ws/{uid}') as ws:
                ws.send_json(auth)
                with self.assertRaises(WebSocketDisconnect) as caught:
                    ws.receive_json()
                self.assertEqual(caught.exception.code, 1008)
            connect.assert_not_awaited()

    def test_socket_requires_authentication_frame(self):
        self.assert_socket_rejected(1, {'type': 'ping'})

    def test_socket_rejects_invalid_token(self):
        self.assert_socket_rejected(1, {'type': 'authenticate', 'token': 'invalid'})

    def test_socket_rejects_spoofed_user_id(self):
        self.assert_socket_rejected(2, {'type': 'authenticate', 'token': encode_token(1)})

    def test_socket_rejects_unknown_user(self):
        self.assert_socket_rejected(999, {'type': 'authenticate', 'token': encode_token(999)})

    def test_socket_accepts_owner_and_cleans_up(self):
        with patch.object(websocket_router, 'SessionLocal', self.sessions), patch.object(websocket_router.websocket_service, 'connect', new_callable=AsyncMock) as connect, patch.object(websocket_router.websocket_service, 'disconnect', new_callable=AsyncMock) as disconnect:
            with self.client.websocket_connect('/ws/1') as ws:
                ws.send_json({'type': 'authenticate', 'token': encode_token(1)})
                ws.send_text('ping')
                self.assertEqual(ws.receive_json()['type'], 'pong')
            connect.assert_awaited_once()
            disconnect.assert_awaited_once()

    def test_database_path_is_independent_of_working_directory(self):
        # 환경 변수보다 이 명시적 값이 우선하고 실제 파일은 생성하지 않는다.
        config = Settings(database_url='sqlite:///./test.db', _env_file=None)
        self.assertEqual(config.database_url, f'sqlite:///{(PROJECT_ROOT / "test.db").as_posix()}')

    def test_clock_preserves_kst_naive_storage(self):
        actual = get_kst_now()
        expected = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
        self.assertIsNone(actual.tzinfo)
        self.assertLess(abs((actual - expected).total_seconds()), 2)

    def test_expired_session_lookup_is_scoped_to_owner(self):
        now = get_kst_now()
        sid = '261028_777'
        with self.sessions() as db:
            db.add_all([SessionLog(user_id=1, session_id=sid, start_time=now-timedelta(minutes=10)), SessionLog(user_id=2, session_id=sid, start_time=now)])
            db.add_all([ChatMessage(user_id=1, session_id=sid, role='user', message='synthetic', turn=1, timestamp=now-timedelta(minutes=5)), ChatMessage(user_id=2, session_id=sid, role='user', message='synthetic', turn=1, timestamp=now)])
            db.commit()
            check_and_close_expired_sessions_for_user(db, 1)
            own = db.query(SessionLog).filter_by(user_id=1, session_id=sid).one()
            other = db.query(SessionLog).filter_by(user_id=2, session_id=sid).one()
            self.assertIsNotNone(own.end_time)
            self.assertIsNone(other.end_time)


if __name__ == '__main__':
    unittest.main()
