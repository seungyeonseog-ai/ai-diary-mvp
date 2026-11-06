"""권한과 보존 이행 검사. 실제 AI·실사용 DB에 연결하지 않는다."""
import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "isolated-access-test"
os.environ["OPENAI_API_KEY"] = "test-only-no-network"
import sqlite3
import json
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.connection import Base
from app.core.access_migration import migrate_access_schema, require_access_schema
from app.models.db.user_model import User
from app.models.db.access_model import AccountAccess, AccountPlanChoice, PilotSurvey
from app.services.access_service import access, ensure_account, permits, choose_plan
from tools.migrate_access import migrate, digest_existing


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"test.db"
        self.engine = create_engine("sqlite:///"+self.path.as_posix())
        # 권한 기반만 필요하므로 관련 테이블만 만든다.
        for table in (User.__table__, AccountAccess.__table__, AccountPlanChoice.__table__, PilotSurvey.__table__):
            table.create(self.engine)
        self.start = datetime(2026,11,3,23,59,59)
        with Session(self.engine) as db:
            db.add_all([User(id=i, username=f"synthetic{i}", email=f"s{i}@example.org",
                            hashed_password="unused", nickname="합성", registered_at=self.start)
                        for i in (1,2)])
            db.commit()

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def test_trial_includes_signup_date_and_ends_at_midnight(self):
        with Session(self.engine) as db:
            self.assertEqual(access(db,1,self.start)["trial_expires_at"], "2026-11-08T00:00:00")
            self.assertTrue(permits(db,1,"weekly",datetime(2026,11,7,23,59,59)))
            self.assertFalse(permits(db,1,"weekly",datetime(2026,11,8)))
            self.assertFalse(permits(db,1,"dialogue",self.start-timedelta(seconds=1)))

    def test_pilot_survey_after_trial_resumes_per_account_and_reuses_plan_choice(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from app.api.routers import access_router as api
        from app.services import posthog_capture
        from app.core.connection import get_db
        from app.api.dependencies.auth_dependencies import get_current_user

        app = FastAPI()
        app.include_router(api.router)

        def database():
            with Session(self.engine) as db:
                yield db

        owner = 1
        app.dependency_overrides[get_db] = database
        root = "/account/pilot-survey"
        experience = {"help_score": 5, "kakao_interest": "unsure", "reason": "synthetic private answer"}
        plan = {"request_id": "pilot", "plan": "dialogue_weekly"}
        analytics = {"POSTHOG_ENVIRONMENT": "validation", "POSTHOG_ID_KEY": "test-key",
                     "POSTHOG_HOST": "https://us.i.posthog.com", "POSTHOG_PROJECT_TOKEN": "test-token"}
        with (TestClient(app) as client,
              patch.object(api, "get_kst_now", return_value=self.start) as clock,
              patch.dict(os.environ, analytics),
              patch.object(posthog_capture, "urlopen") as transport):
            self.assertEqual(client.get(root).status_code, 401)
            app.dependency_overrides[get_current_user] = lambda: User(id=owner)
            self.assertFalse(client.get(root).json()["available"])
            self.assertEqual(client.post(root + "/experience", json=experience).status_code, 409)
            transport.assert_not_called()
            clock.return_value = datetime(2026, 11, 10)
            self.assertTrue(client.get(root).json()["available"])
            for _ in range(2):
                self.assertEqual(client.post(root + "/experience", json=experience).status_code, 200)
            self.assertEqual(client.get(root).json(), {
                "available": True, "experience_submitted": True, "plan_submitted": False,
            })
            self.assertEqual(client.post(root + "/plan", json={**plan, "plan": "combo"}).status_code, 422)
            for _ in range(2):
                self.assertEqual(client.post(root + "/plan", json=plan).status_code, 200)
            self.assertTrue(client.get(root).json()["plan_submitted"])
            access_state = client.get("/account/access").json()
            self.assertEqual(access_state["selected_plan"], "dialogue_weekly")
            self.assertEqual(access_state["features"], [])
            owner = 2
            self.assertFalse(client.get(root).json()["experience_submitted"])
            self.assertFalse(client.get(root).json()["plan_submitted"])
        events = [json.loads(call.args[0].data) for call in transport.call_args_list]
        self.assertEqual([event["event"] for event in events],
                         ["pilot_experience_submitted", "pilot_plan_submitted"])
        experience_props, plan_props = [event["properties"] for event in events]
        self.assertEqual(experience_props["distinct_id"], plan_props["distinct_id"])
        self.assertEqual(experience_props["help_score"], 5)
        self.assertEqual(experience_props["kakao_interest"], "unsure")
        self.assertNotIn(experience["reason"], json.dumps(events))
        self.assertEqual(plan_props["plan"], "dialogue_weekly")
        self.assertCountEqual(plan_props["selected_features"], ["dialogue", "weekly"])
        self.assertEqual(plan_props["occurred_at"], "2026-11-10T00:00:00+09:00")
        with Session(self.engine) as db:
            self.assertEqual(db.query(AccountPlanChoice).count(), 1)
            self.assertEqual(db.get(PilotSurvey, 1).help_score, 5)

    def test_choice_api_authenticated_account_isolated_idempotent_and_never_grants_access(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from app.api.routers import access_router as api
        from app.core.connection import get_db
        from app.api.dependencies.auth_dependencies import get_current_user
        app=FastAPI();app.include_router(api.router)
        def database():
            with Session(self.engine) as db:yield db
        app.dependency_overrides[get_db]=database
        with TestClient(app) as client, patch.object(api,"get_kst_now",return_value=datetime(2026,11,11)):
            self.assertEqual(client.get('/account/access').status_code,401)
            app.dependency_overrides[get_current_user]=lambda:User(id=1)
            before=client.get('/account/access').json()
            payload={"request_id":"choice","plan":"super"}
            for _ in range(2):
                response=client.post('/account/plan-choice',json=payload)
                self.assertEqual(response.status_code,200,response.text)
                self.assertFalse(response.json()['grants_access'])
            after=client.get('/account/access').json()
            self.assertEqual(after['selected_plan'],'super')
            for field in ('features','plan','trial_expires_at'):
                self.assertEqual(before[field],after[field])
            self.assertEqual(after['features'],[])
            self.assertEqual(client.post('/account/plan-choice',json={**payload,'plan':'free'}).status_code,409)
            self.assertEqual(client.post('/account/plan-choice',json={**payload,'user_id':2}).status_code,422)
            self.assertEqual(client.post('/account/plan-choice',json={**payload,'plan':'bogus'}).status_code,422)
            app.dependency_overrides[get_current_user]=lambda:User(id=2)
            self.assertIsNone(client.get('/account/access').json()['selected_plan'])
        with Session(self.engine) as db:self.assertEqual(db.query(AccountPlanChoice).count(),1)

    def test_legacy_start_and_unknown_registration_are_preserved(self):
        with Session(self.engine) as db:
            user = db.get(User,1)
            user.registered_at = None
            user.trial_started_at = datetime(2026,11,2,15)
            ensure_account(db,user)
            self.assertEqual(access(db,1,self.start)["trial_expires_at"],"2026-11-07T00:00:00")
            user = db.get(User,2)
            user.registered_at = None
            self.assertEqual(access(db,2,self.start)["trial_state"],"registration_unknown")
            self.assertEqual(access(db,2,self.start)["features"],[])

    def test_all_combinations_only_save_preference_before_and_after_trial(self):
        with Session(self.engine) as db:
            before=access(db,1,self.start)
            for index,plan in enumerate(('free','dialogue_encouragement','dialogue_weekly','encouragement_weekly','super')):
                choose_plan(db,1,str(index),plan,self.start)
                self.assertEqual(access(db,1,self.start),before)
                self.assertEqual(access(db,1,datetime(2026,11,10))['features'],[])
            self.assertEqual(db.query(AccountPlanChoice).count(),5)
            self.assertEqual(access(db,1,datetime(2026,11,10))['plan'],'free')

    def test_legacy_paid_fields_cannot_extend_trial_or_grant_features(self):
        with Session(self.engine) as db:
            row=ensure_account(db,db.get(User,1))
            row.plan="super"
            self.assertEqual(access(db,1,datetime(2026,11,10))["features"],[])
            self.assertEqual(access(db,1,datetime(2026,11,10))["plan"],"free")

    def test_existing_period_and_account_isolation_survive_repeat_migration(self):
        with Session(self.engine) as db:
            ensure_account(db,db.get(User,1))
            db.get(User,2).registered_at=datetime(2026,10,1)
            db.commit()
        migrate_access_schema(self.engine)
        with Session(self.engine) as db:
            self.assertTrue(permits(db,1,"dialogue",self.start))
            self.assertFalse(permits(db,2,"dialogue",self.start))
            snapshot=db.get(AccountAccess,1).trial_expires_at
        migrate_access_schema(self.engine)
        with Session(self.engine) as db:self.assertEqual(db.get(AccountAccess,1).trial_expires_at,snapshot)

    def test_signup_transaction_uses_explicit_clock_and_stores_period(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from app.services import auth_service
        with Session(self.engine) as db, patch.object(auth_service,"get_kst_now",return_value=self.start), patch.object(auth_service,"get_password_hash",return_value="unused"):
            user=auth_service.create_user(db,SimpleNamespace(username="new",email="new@example.org",password="synthetic",nickname="합성"))
            row=db.get(AccountAccess,user.id)
            self.assertEqual(user.registered_at,self.start)
            self.assertEqual(row.trial_started_at,self.start)
            self.assertEqual(row.trial_expires_at,datetime(2026,11,8))

    def test_writing_api_uses_midnight_expiry_and_preserves_free_base(self):
        from unittest.mock import patch
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.routers import writing_router as api
        from app.api.dependencies.auth_dependencies import get_current_user
        from app.core.connection import get_db,Base
        from app.services import writing_service
        # 실제 작성 라우터의 조회 응답까지 검사하며 AI 요청은 하지 않는다.
        Base.metadata.create_all(self.engine)
        app=FastAPI();app.include_router(api.router)
        owner=[1];now=[datetime(2026,11,7,23,59,59)]
        def database():
            with Session(self.engine) as db:yield db
        app.dependency_overrides[get_db]=database
        app.dependency_overrides[get_current_user]=lambda:User(id=owner[0])
        with TestClient(app) as client, patch.object(writing_service,"get_kst_now",side_effect=lambda:now[0]), patch.object(api,"get_kst_now",side_effect=lambda:now[0]):
            key=client.post("/writing").json()["id"]
            quota=client.get("/writing/"+key).json()["quota"]
            self.assertEqual(quota["extra_remaining"],2)
            self.assertEqual(quota["trial_expires_at"],"2026-11-08T00:00:00")
            now[0]=datetime(2026,11,10)
            key=client.post("/writing").json()["id"]
            quota=client.get("/writing/"+key).json()["quota"]
            self.assertEqual((quota["base_remaining"],quota["extra_remaining"]),(1,0))
            self.assertEqual(quota["features"],[])
            owner[0]=2
            self.assertEqual(client.get("/writing/"+key).status_code,404)

    def test_backup_migration_all_original_values_unchanged_and_repeat_safe(self):
        # 기존 서버에는 이용권 테이블이 없으며 사용자 원본은 변경하지 않아야 한다.
        AccountAccess.__table__.drop(self.engine)
        with closing(sqlite3.connect(self.path)) as db:
            before = digest_existing(db)
        backup = migrate(self.path)
        require_access_schema(self.engine)
        with Session(self.engine) as db:
            trial = db.get(AccountAccess,1).trial_expires_at
            self.assertEqual(trial,datetime(2026,11,8))
        migrate_access_schema(self.engine)
        with closing(sqlite3.connect(self.path)) as db, closing(sqlite3.connect(backup)) as original:
            self.assertEqual(digest_existing(db),before)
            self.assertEqual(digest_existing(original),before)
        with Session(self.engine) as db:
            self.assertEqual(db.query(AccountAccess).count(),2)
            self.assertEqual(db.get(AccountAccess,1).trial_expires_at,trial)


if __name__ == "__main__":
    unittest.main()
