"""합성 계정·메모리 DB로 실제 로그인→보호 API와 만료 후 재로그인을 확인한다."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-only-no-real-user-secret'
os.environ['OPENAI_API_KEY'] = 'test-only-no-network'

import unittest
from datetime import datetime, timedelta, timezone
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.api.routers import auth_router
from app.api.dependencies.auth_dependencies import get_current_user
from app.core.connection import Base, get_db
from app.core.token_utils import SECRET_KEY, ALGORITHM
from app.models.db.user_model import User
from app.services.auth_service import get_password_hash


class LoginRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(bind=cls.engine)
        with cls.sessions() as db:
            db.add(User(id=1, username='synthetic', email='synthetic@example.test', nickname='tester', hashed_password=get_password_hash('TestOnly123!')))
            db.commit()
        cls.app = FastAPI()
        cls.app.include_router(auth_router.router)
        def isolated_db():
            with cls.sessions() as db:
                yield db
        cls.app.dependency_overrides[get_db] = isolated_db
        cls.app.dependency_overrides[auth_router.get_db] = isolated_db
        @cls.app.get('/protected')
        def protected(user=Depends(get_current_user)):
            return {'user_id': user.id}
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.engine.dispose()

    def test_login_issues_usable_token(self):
        response = self.client.post('/login', json={'username': 'synthetic', 'password': 'TestOnly123!'})
        self.assertEqual(response.status_code, 200)
        token = response.json()['access_token']
        response = self.client.get('/protected', headers={'Authorization': 'Bearer ' + token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'user_id': 1})

    def test_expired_token_rejected_then_login_recovers(self):
        token = jwt.encode({'user_id': 1, 'exp': datetime.now(timezone.utc) - timedelta(minutes=1)}, SECRET_KEY, algorithm=ALGORITHM)
        self.assertEqual(self.client.get('/protected', headers={'Authorization': 'Bearer ' + token}).status_code, 401)
        self.test_login_issues_usable_token()

    def test_wrong_password_does_not_issue_token(self):
        response = self.client.post('/login', json={'username': 'synthetic', 'password': 'wrong'})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('access_token', response.json())
