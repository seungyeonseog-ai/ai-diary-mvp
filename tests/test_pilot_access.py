"""격리 DB로 초대 가입·로그인·기존 토큰 차단 검증."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'pilot-access-test-only-secret-key'
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.connection import Base, get_db
from app.api.routers import auth_router
from app.core.token_utils import encode_token
from app.models.db.user_model import User
from app.models.db import access_model
from app.services.auth_service import get_password_hash
from app.utils.time_utils import get_kst_now


class PilotAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine('sqlite:///'+str(Path(self.temp.name)/'test.db'), connect_args={'check_same_thread':False})
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            for uid in (1,2):
                db.add(User(id=uid, username=f'existing{uid}', email=f'existing{uid}@example.org',
                            nickname='합성', hashed_password=get_password_hash('Test!2026'), registered_at=get_kst_now()))
            db.commit()
        self.env = patch.dict(os.environ, {'PILOT_ACCESS_MODE':'restricted', 'PILOT_ALLOWED_USER_IDS':'1',
            'PILOT_INVITATIONS':json.dumps({'invited':{'email':'invited@example.org','digest':hashlib.sha256(b'synthetic-invite').hexdigest()}})})
        self.env.start()
        app = FastAPI(); app.include_router(auth_router.router)
        def isolated():
            with Session(self.engine) as db: yield db
        app.dependency_overrides[get_db] = isolated
        app.dependency_overrides[auth_router.get_db] = isolated
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close(); self.env.stop(); self.engine.dispose(); self.temp.cleanup()

    def test_existing_login_and_old_token_are_both_gated(self):
        for uid, status in ((1,200),(2,403)):
            self.assertEqual(self.client.post('/login',json={'username':f'existing{uid}','password':'Test!2026'}).status_code,status)
            self.assertEqual(self.client.get('/account/me',headers={'Authorization':'Bearer '+encode_token(uid)}).status_code,status)
        with patch.dict(os.environ, {'PILOT_ALLOWED_USER_IDS':''}):
            self.assertEqual(self.client.get('/account/me',headers={'Authorization':'Bearer '+encode_token(1)}).status_code,403)

    def test_invitation_binds_name_email_secret_and_cannot_register_twice(self):
        payload={'username':'invited','email':'invited@example.org','password':'Test!2026','nickname':'합성','invite_code':'synthetic-invite'}
        for fields in ({'invite_code':None},{'invite_code':'wrong'},{'username':'other'},{'email':'other@example.org'}):
            self.assertEqual(self.client.post('/register',json={**payload,**fields}).status_code,403)
        self.assertEqual(self.client.post('/register',json=payload).status_code,200)
        self.assertEqual(self.client.post('/register',json=payload).status_code,400)
        response=self.client.post('/login',json={'username':'invited','password':'Test!2026'})
        self.assertEqual(response.status_code,200)
        token=response.json()['access_token']
        self.assertEqual(self.client.get('/account/me',headers={'Authorization':'Bearer '+token}).status_code,200)
        with patch.dict(os.environ, {'PILOT_INVITATIONS':'{}'}):
            self.assertEqual(self.client.get('/account/me',headers={'Authorization':'Bearer '+token}).status_code,403)

    def test_bad_or_empty_config_fails_closed_and_local_open_compatibility(self):
        for value in ('', 'not-json', '[]'):
            with patch.dict(os.environ, {'PILOT_ALLOWED_USER_IDS':'','PILOT_INVITATIONS':value}):
                self.assertEqual(self.client.post('/login',json={'username':'existing1','password':'Test!2026'}).status_code,403)
        with patch.dict(os.environ, {'PILOT_ACCESS_MODE':'open'}):
            self.assertEqual(self.client.post('/login',json={'username':'existing2','password':'Test!2026'}).status_code,200)
