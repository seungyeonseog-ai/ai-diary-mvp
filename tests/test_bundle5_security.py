"""사용자 DB/외부 API 없이 추가 보안 경로 검사."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'isolated-security-test'
os.environ['OPENAI_API_KEY'] = 'test-placeholder'
import unittest
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.connection import Base, get_db
from app.core.token_utils import encode_token
from app.models.db.user_model import User
from app.models.db.login_log import LoginLog
from app.api.routers import auth_router

class LogoutSecurityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            for uid in (1, 2):
                db.add(User(id=uid, username=f'u{uid}', email=f'u{uid}@example.test', hashed_password='unused', nickname='tester'))
                db.add(LoginLog(id=uid, user_id=uid, login_time=datetime(2026,10,29)))
            db.add(LoginLog(id=3, user_id=1, login_time=datetime(2026,10,28)))
            db.commit()
        app = FastAPI()
        app.include_router(auth_router.router)
        def isolated_db():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = isolated_db
        app.dependency_overrides[auth_router.get_db] = isolated_db
        self.client = TestClient(app)
    def tearDown(self):
        self.client.close()
        self.engine.dispose()
    def test_requires_authentication_without_changes(self):
        for headers in ({}, {'Authorization':'Bearer invalid'}, {'Authorization':f'Bearer {encode_token(999)}'}):
            self.assertEqual(self.client.post('/logout', json={'user_id':2}, headers=headers).status_code,401)
        with self.sessions() as db:
            self.assertTrue(all(row.logout_time is None for row in db.query(LoginLog)))
    def test_body_cannot_select_other_account_and_retry_preserves_timestamp(self):
        headers={'Authorization': f'Bearer {encode_token(1)}'}
        self.assertEqual(self.client.post('/logout', json={'user_id':2},headers=headers).status_code,200)
        with self.sessions() as db:
            first=db.get(LoginLog,1).logout_time
            self.assertIsNotNone(first)
            self.assertIsNone(db.get(LoginLog,2).logout_time)
            self.assertIsNone(db.get(LoginLog,3).logout_time)
        self.assertEqual(self.client.post('/logout',headers=headers).status_code,200)
        with self.sessions() as db:
            self.assertEqual(db.get(LoginLog,1).logout_time,first)
    def test_no_login_record_is_safe(self):
        with self.sessions() as db:
            db.query(LoginLog).filter_by(user_id=2).delete()
            db.commit()
        self.assertEqual(self.client.post('/logout',headers={'Authorization':f'Bearer {encode_token(2)}'}).status_code,200)

if __name__ == '__main__': unittest.main()
