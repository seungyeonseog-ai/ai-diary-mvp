"""묶음6: 안내 완료 기록의 인증·계정 격리·멱등성·추가형 이행."""
import unittest
from datetime import datetime
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests import test_access_policy as support
from app.api.routers import access_router as api
from app.api.dependencies.auth_dependencies import get_current_user
from app.core.connection import get_db
from app.core.access_migration import migrate_access_schema
from app.models.db.user_model import User
from app.models.db.access_model import AccountAccess

class OnboardingTests(unittest.TestCase):
 def setUp(self):
  self.f=support.AccessTests();self.f.setUp();self.owner=1;app=FastAPI();app.include_router(api.router)
  def database():
   with Session(self.f.engine) as db:yield db
  app.dependency_overrides[get_db]=database
  self.app=app;self.client=TestClient(app);self.clock=patch.object(api,'get_kst_now',return_value=self.f.start);self.mock_clock=self.clock.start()
 def tearDown(self):self.clock.stop();self.client.close();self.f.tearDown()
 def login(self):self.app.dependency_overrides[get_current_user]=lambda:User(id=self.owner)
 def test_unauthenticated_cannot_read_or_complete(self):
  self.assertEqual(self.client.get('/account/access').status_code,401)
  self.assertEqual(self.client.post('/account/onboarding').status_code,401)
 def test_complete_is_idempotent_and_preserves_access_period(self):
  self.login();before=self.client.get('/account/access').json();self.assertFalse(before['onboarding_complete'])
  for _ in range(2):self.assertEqual(self.client.post('/account/onboarding').json(),{'complete':True})
  after=self.client.get('/account/access').json();self.assertTrue(after['onboarding_complete'])
  for key in ('features','plan','trial_started_at','trial_expires_at','selected_plan'):self.assertEqual(before[key],after[key])
  with Session(self.f.engine) as db:self.assertEqual(db.get(AccountAccess,1).onboarding_completed_at,self.f.start)
 def test_other_account_remains_unconfigured(self):
  self.login();self.client.post('/account/onboarding');self.owner=2
  self.assertFalse(self.client.get('/account/access').json()['onboarding_complete'])
 def test_repeat_migration_preserves_onboarding_and_trial(self):
  self.login();self.client.post('/account/onboarding');before=self.client.get('/account/access').json()
  migrate_access_schema(self.f.engine);migrate_access_schema(self.f.engine)
  self.assertEqual(self.client.get('/account/access').json(),before)
 def test_expiry_does_not_repeat_trial_or_grant_access(self):
  self.login();self.client.post('/account/onboarding');self.mock_clock.return_value=datetime(2026,11,10)
  after=self.client.get('/account/access').json();self.assertTrue(after['onboarding_complete']);self.assertEqual(after['features'],[])

if __name__=='__main__':unittest.main()
