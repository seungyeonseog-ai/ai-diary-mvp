"""5일 신규 정책과 저장된 7일 계정/결과의 공존 검증."""
import unittest
from datetime import datetime
from sqlalchemy.orm import Session
from tests.test_weekly_cycle import WeeklyCycleTests, fake
from app.models.db.access_model import AccountAccess
from app.models.db.study_model import WeeklyAnalysisReport
from app.services import weekly_cycle_service as svc
from app.services.access_service import access
from app.repositories.weekly_analysis_repository import WeeklyAnalysisRepository


class FiveDayTests(unittest.TestCase):
    setUp = WeeklyCycleTests.setUp
    tearDown = WeeklyCycleTests.tearDown
    chat = WeeklyCycleTests.chat
    tick = WeeklyCycleTests.tick
    count = WeeklyCycleTests.count

    def use_five_days(self):
        with Session(self.engine) as db:
            db.get(AccountAccess, 1).trial_expires_at = datetime(2026, 11, 6)
            db.commit()

    def test_five_days_three_sources_boundary_and_old_seven_day_account(self):
        self.use_five_days()
        for day in (1, 2, 3): self.chat(day)
        self.tick(datetime(2026, 11, 3, 23, 51))
        self.assertEqual(self.count(WeeklyAnalysisReport), 0)
        self.tick(datetime(2026, 11, 5, 23, 49))
        self.assertEqual(self.count(WeeklyAnalysisReport), 0)
        self.tick(datetime(2026, 11, 5, 23, 51))
        self.tick(datetime(2026, 11, 5, 23, 52))
        with Session(self.engine) as db:
            report = db.query(WeeklyAnalysisReport).one()
            self.assertEqual(report.week_end_date.date().isoformat(), '2026-11-05')
            self.assertEqual(len(WeeklyAnalysisRepository(db).get_analysis_sources(report)), 3)
            self.assertEqual(access(db, 1, datetime(2026, 11, 5))['cycle_days'], 5)
            self.assertEqual(access(db, 2, datetime(2026, 11, 5))['cycle_days'], 7)
            self.assertEqual(svc.status(db, 1, datetime(2026, 11, 6))['end'], '2026-11-10')
            self.assertEqual(access(db, 1, datetime(2026, 11, 6))['features'], [])
        weekly_calls = [c for c in self.ai.call_args_list if c.args[0] != 'daily']
        self.assertEqual(len(weekly_calls), 3)
        self.assertTrue(all(c.args[1]['period_days'] == 5 for c in weekly_calls))

    def test_two_days_not_enough(self):
        self.use_five_days()
        for day in (1, 5): self.chat(day)
        self.tick(datetime(2026, 11, 5, 23, 51))
        self.assertEqual(self.count(WeeklyAnalysisReport), 0)

    def test_all_five_days_readable_and_account_isolated(self):
        self.use_five_days()
        for day in range(1, 6): self.chat(day)
        self.tick(datetime(2026, 11, 5, 23, 51))
        with Session(self.engine) as db:
            report = db.query(WeeklyAnalysisReport).one()
            self.assertEqual(len(WeeklyAnalysisRepository(db).get_analysis_sources(report)), 5)
            report.user_id = 2
            with self.assertRaises(Exception):
                WeeklyAnalysisRepository(db).get_analysis_sources(report)


if __name__ == '__main__': unittest.main()
