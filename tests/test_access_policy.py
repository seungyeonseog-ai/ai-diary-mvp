"""권한과 보존 이행 검사. 실제 AI·실사용 DB에 연결하지 않는다."""
import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "isolated-access-test"
os.environ["OPENAI_API_KEY"] = "test-only-no-network"
import sqlite3
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
from app.models.db.access_model import AccountAccess, AccessChange
from app.services.access_service import access, ensure_account, permits, update_pass
from tools.migrate_access import migrate, digest_existing


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"test.db"
        self.engine = create_engine("sqlite:///"+self.path.as_posix())
        # 권한 기반만 필요하므로 관련 테이블만 만든다.
        for table in (User.__table__, AccountAccess.__table__, AccessChange.__table__):
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
            self.assertEqual(access(db,1,self.start)["trial_expires_at"], "2026-11-10T00:00:00")
            self.assertTrue(permits(db,1,"weekly",datetime(2026,11,9,23,59,59)))
            self.assertFalse(permits(db,1,"weekly",datetime(2026,11,10)))
            self.assertFalse(permits(db,1,"dialogue",self.start-timedelta(seconds=1)))

    def test_legacy_start_and_unknown_registration_are_preserved(self):
        with Session(self.engine) as db:
            user = db.get(User,1)
            user.registered_at = None
            user.trial_started_at = datetime(2026,11,2,15)
            ensure_account(db,user)
            self.assertEqual(access(db,1,self.start)["trial_expires_at"],"2026-11-09T00:00:00")
            user = db.get(User,2)
            user.registered_at = None
            self.assertEqual(access(db,2,self.start)["trial_state"],"registration_unknown")
            self.assertEqual(access(db,2,self.start)["features"],[])

    def test_pass_combinations_change_cancel_expire_and_account_isolation(self):
        now = datetime(2026,11,11)
        end = now+timedelta(days=30)
        with Session(self.engine) as db:
            update_pass(db,1,"first","dialogue_encouragement",now,end)
            self.assertEqual(set(access(db,1,now)["features"]),{"dialogue","encouragement"})
            self.assertEqual(access(db,2,now)["features"],[])
            update_pass(db,1,"second","encouragement_weekly",now+timedelta(days=1),end+timedelta(days=10))
            self.assertEqual(set(access(db,1,now+timedelta(days=1))["features"]),{"encouragement","weekly"})
            self.assertEqual(db.get(AccountAccess,1).pass_expires_at,end)
            update_pass(db,1,"third","encouragement_weekly",now+timedelta(days=2),cancel=True)
            db.flush()
            self.assertTrue(permits(db,1,"weekly",end-timedelta(seconds=1)))
            self.assertEqual(access(db,1,end)["features"],[])
            self.assertEqual(db.query(AccessChange).count(),3)

    def test_idempotent_changes_invalid_grant_and_conflicting_key(self):
        now = datetime(2026,11,11)
        with Session(self.engine) as db:
            for plan,end in (("free",None),("super",None),("bogus",now+timedelta(days=1))):
                with self.assertRaises(ValueError): update_pass(db,1,plan,plan,now,end)
            for _ in range(2):
                update_pass(db,1,"request","super",now,now+timedelta(days=30))
                db.flush()
            self.assertEqual(db.query(AccessChange).count(),1)
            with self.assertRaises(ValueError):
                update_pass(db,1,"request","dialogue_weekly",now)

    def test_backup_migration_all_original_values_unchanged_and_repeat_safe(self):
        # 기존 서버에는 이용권 테이블이 없으며 사용자 원본은 변경하지 않아야 한다.
        AccessChange.__table__.drop(self.engine)
        AccountAccess.__table__.drop(self.engine)
        with closing(sqlite3.connect(self.path)) as db:
            before = digest_existing(db)
        backup = migrate(self.path)
        require_access_schema(self.engine)
        with Session(self.engine) as db:
            trial = db.get(AccountAccess,1).trial_expires_at
            self.assertEqual(trial,datetime(2026,11,10))
        migrate_access_schema(self.engine)
        with closing(sqlite3.connect(self.path)) as db, closing(sqlite3.connect(backup)) as original:
            self.assertEqual(digest_existing(db),before)
            self.assertEqual(digest_existing(original),before)
        with Session(self.engine) as db:
            self.assertEqual(db.query(AccountAccess).count(),2)
            self.assertEqual(db.get(AccountAccess,1).trial_expires_at,trial)


if __name__ == "__main__":
    unittest.main()
