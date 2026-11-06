import os
os.environ.setdefault('DATABASE_URL','sqlite:///:memory:')
os.environ.setdefault('OPENAI_API_KEY','test-only-no-network')
import tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.connection import Base
from app.models.db.user_model import User
from app.models.db.session_log import SessionLog
from app.models.db.chat_message_model import ChatMessage
from app.models.db.writing_model import Writing
from app.models.db.study_model import DiaryAnalysisReport,WeeklyAnalysisReport
from app.models.db.weekly_cycle_model import AnalysisJob,WeeklyClock
from app.models.db.daily_model import ResultNotice
from app.core.weekly_migration import migrate_weekly_schema
from app.services import weekly_cycle_service as svc
from app.repositories.weekly_analysis_repository import WeeklyAnalysisRepository
from app.services.access_service import ensure_account
from app.models.db.access_model import AccountAccess

DAILY={'emotions':['기쁨','피곤'],'scores':[.6,-.4],'keywords':['정리'],'keyword_descriptions':['정리를 마쳤어요.'],'summary':'합성 하루였어요.'}
def fake(kind,data):
    if kind=='daily':return dict(DAILY)
    if kind=='emotion':return {'trend':'흐름','dominant_emotion':'기쁨','recommendation':'쉬어가세요.'}
    if kind=='keyword':return {'main_themes':['정리'],'recurring_patterns':['조금씩'],'insights':'차분했어요.'}
    return {'overall_assessment':'잘 마쳤어요.','life_satisfaction':.5}


class WeeklyCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.engine=create_engine('sqlite:///'+str(Path(self.tmp.name)/'test.db'),connect_args={'check_same_thread':False,'timeout':15})
        Base.metadata.create_all(self.engine);migrate_weekly_schema(self.engine,datetime(2026,11,1))
        self.ai=Mock(side_effect=fake)
        with Session(self.engine) as db:
            for uid in (1,2):db.add(User(id=uid,username=f'w{uid}',email=f'w{uid}@example.org',nickname='합성',hashed_password='unused',registered_at=datetime(2026,11,1)))
            db.flush()
            for uid in (1,2):
                row=ensure_account(db,db.get(User,uid));row.trial_expires_at=datetime(2026,11,8)
            db.commit()
    def tearDown(self):self.engine.dispose();self.tmp.cleanup()
    def chat(self,day,hour=12,minute=0,uid=1,role='user'):
        with Session(self.engine) as db:
            row=ChatMessage(user_id=uid,session_id='synthetic',role=role,message='짧은 합성 대화',turn=1,timestamp=datetime(2026,11,day,hour,minute));db.add(row);db.commit();return row.id
    def tick(self,now):
        for _ in range(2):
            for key in svc.dispatch(self.engine,now):svc.run(self.engine,key,generate=self.ai,now=now)
    def count(self,model):
        with Session(self.engine) as db:return db.query(model).count()
    def test_expired_weekly_access_keeps_daily_but_skips_weekly(self):
        with Session(self.engine) as db:
            row=db.get(AccountAccess,1);row.trial_started_at=None;row.trial_expires_at=None
            db.commit()
        for day in (1,3,7):self.chat(day)
        self.tick(datetime(2026,11,7,23,51))
        self.assertEqual(self.count(DiaryAnalysisReport),3)
        self.assertEqual(self.count(WeeklyAnalysisReport),0)
        self.assertEqual([c.args[0] for c in self.ai.call_args_list],['daily']*3)

    def test_weekly_right_revoked_during_generation_publishes_nothing(self):
        for day in (1,3,7):self.chat(day)
        original=self.ai.side_effect
        def revoked(kind,*args):
            result=original(kind,*args)
            if kind=='emotion':
                with Session(self.engine) as db:
                    row=db.get(AccountAccess,1);row.trial_started_at=None;row.trial_expires_at=None
                    db.commit()
            return result
        self.ai.side_effect=revoked
        self.tick(datetime(2026,11,7,23,51))
        self.assertEqual(self.count(WeeklyAnalysisReport),0)
        self.assertEqual(self.count(ResultNotice),0)
        self.assertNotIn('keyword',[c.args[0] for c in self.ai.call_args_list])
        with Session(self.engine) as db:
            job=db.get(AnalysisJob,'1:weekly:2026-11-07')
            self.assertEqual(job.state,'skipped');self.assertIsNone(job.retry_at)
    def test_first_dialogue_anchor_not_registration_and_no_day3_weekly(self):
        for day in (2,3,4):self.chat(day)
        self.tick(datetime(2026,11,4,23,51))
        with Session(self.engine) as db:self.assertEqual(db.get(WeeklyClock,1).anchor_date,'2026-11-02')
        self.assertEqual(self.count(DiaryAnalysisReport),3);self.assertEqual(self.count(WeeklyAnalysisReport),0)
        # 가입 다음날 첫 사용이면 첫 주간 도착 전 체험이 끝나며 연장하지 않는다.
        self.tick(datetime(2026,11,8,23,51));self.assertEqual(self.count(WeeklyAnalysisReport),0)
    def test_cutoff_and_midnight_finish_original_day(self):
        before=self.chat(1,23,49);self.chat(1,23,55)
        keys=svc.dispatch(self.engine,datetime(2026,11,1,23,50))
        for key in keys:svc.run(self.engine,key,generate=self.ai,now=datetime(2026,11,2,0,2))
        with Session(self.engine) as db:
            row=db.query(DiaryAnalysisReport).one();self.assertEqual(row.date_str,'2026-11-01')
            self.assertEqual(db.get(AnalysisJob,'1:daily:2026-11-01').source_ids,[before])
        self.assertEqual(self.ai.call_count,1)
    def test_before_cutoff_no_generation_and_short_text_allowed(self):
        self.chat(1);self.tick(datetime(2026,11,1,23,49));self.assertEqual(self.ai.call_count,0)
        self.tick(datetime(2026,11,1,23,50));self.assertEqual(self.ai.call_count,1)
    def test_last_ten_minutes_only_no_fake_analysis(self):
        self.chat(1,23,55);self.tick(datetime(2026,11,2));self.assertEqual(self.count(DiaryAnalysisReport),0)
    def test_three_days_cycle_and_next_period_no_reuse(self):
        for day in (1,3,7):self.chat(day)
        self.tick(datetime(2026,11,7,23,51));self.tick(datetime(2026,11,7,23,52))
        self.assertEqual(self.count(WeeklyAnalysisReport),1);self.assertEqual(self.ai.call_count,6)
        self.chat(8);self.chat(9);self.tick(datetime(2026,11,14,23,51))
        self.assertEqual(self.count(WeeklyAnalysisReport),1)
    def test_three_to_seven_sources_and_no_radar_fields(self):
        for day in (1,3,7):self.chat(day)
        self.tick(datetime(2026,11,7,23,51))
        with Session(self.engine) as db:
            report=db.query(WeeklyAnalysisReport).one();rows=WeeklyAnalysisRepository(db).get_analysis_sources(report)
            self.assertEqual([r.date_str for r in rows],['2026-11-01','2026-11-03','2026-11-07'])
            self.assertNotIn('life_satisfaction',report.comprehensive_pattern_result)
            report.user_id=2
            with self.assertRaises(Exception):WeeklyAnalysisRepository(db).get_analysis_sources(report)
    def test_missing_daily_recovery_blocks_weekly_until_ready(self):
        for day in (1,3,7):self.chat(day)
        self.ai.side_effect=RuntimeError();self.tick(datetime(2026,11,7,23,51));self.assertEqual(self.count(WeeklyAnalysisReport),0)
        self.ai.side_effect=fake;self.tick(datetime(2026,11,7,23,59));self.assertEqual(self.count(WeeklyAnalysisReport),1)
    def test_phase_checkpoint_avoids_repeat_successful_calls(self):
        for day in (1,3,7):self.chat(day)
        self.tick(datetime(2026,11,7,23,50))
        # 이미완료결과 재실행은AI/알림을늘리지않음.
        count=self.ai.call_count;self.tick(datetime(2026,11,8));self.assertEqual(self.ai.call_count,count);self.assertEqual(self.count(ResultNotice),1)
    def test_partial_weekly_failure_reuses_emotion_checkpoint(self):
        for day in (1,3,7):self.chat(day)
        def fail_keyword(kind,data):
            if kind=='keyword':raise RuntimeError('synthetic')
            return fake(kind,data)
        self.ai.side_effect=fail_keyword;self.tick(datetime(2026,11,7,23,51))
        self.assertEqual(self.count(WeeklyAnalysisReport),0)
        before=sum(c.args[0]=='emotion' for c in self.ai.call_args_list)
        self.ai.side_effect=fake;self.tick(datetime(2026,11,7,23,59))
        self.assertEqual(self.count(WeeklyAnalysisReport),1)
        self.assertEqual(sum(c.args[0]=='emotion' for c in self.ai.call_args_list),before)
    def test_eligibility_ignores_other_account_and_assistant(self):
        self.chat(1);self.chat(3,uid=2);self.chat(7,role='assistant')
        self.tick(datetime(2026,11,7,23,51));self.assertEqual(self.count(WeeklyAnalysisReport),0)
    def test_existing_dialogue_before_activation_does_not_anchor(self):
        with Session(self.engine) as db:
            from app.models.db.weekly_cycle_model import WeeklyActivation
            db.get(WeeklyActivation,1).activated_at=datetime(2026,11,3);db.commit()
        self.chat(1);self.chat(4);self.tick(datetime(2026,11,4,23,51))
        with Session(self.engine) as db:self.assertEqual(db.get(WeeklyClock,1).anchor_date,'2026-11-04')
    def test_concurrent_worker_one_daily_ai_call(self):
        self.chat(1);keys=svc.dispatch(self.engine,datetime(2026,11,1,23,50))
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:svc.run(self.engine,keys[0],generate=self.ai,now=datetime(2026,11,1,23,50)),range(2)))
        self.assertEqual(self.ai.call_count,1);self.assertEqual(self.count(DiaryAnalysisReport),1)
    def test_pre_activation_data_not_retroactively_analyzed(self):
        self.chat(1);migrate_weekly_schema(self.engine,datetime(2026,11,5))
        self.tick(datetime(2026,11,7,23,51));self.assertEqual(self.count(DiaryAnalysisReport),1)
        # 재이행은기존활성화일을초기화하지않는다.


if __name__=='__main__':unittest.main()
