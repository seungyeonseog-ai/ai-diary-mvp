"""고정 KST 시각·파일 SQLite·실제 API, 외부 AI는 주입한다."""
import os
import json
os.environ.setdefault('DATABASE_URL','sqlite:///:memory:')
os.environ.setdefault('OPENAI_API_KEY','test-only-no-network')
os.environ.setdefault('SECRET_KEY','daily-test-only')
import tempfile
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock,patch
from sqlalchemy import create_engine,text
from sqlalchemy.orm import Session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core.connection import Base,get_db
from app.models.db.user_model import User
from app.models.db.chat_message_model import ChatMessage
from app.models.db.study_model import EncouragementReport,DiaryReport
from app.models.db.daily_model import DailyJob,DailyActivation,LetterDelivery,ResultNotice
from app.models.db.writing_model import SummaryRange
from app.services import daily_service as svc
from app.services import writing_service as writing
from app.core.daily_migration import migrate_daily_schema
from app.api.routers import daily_router as api
from app.api.dependencies.auth_dependencies import get_current_user


class DailyTests(unittest.TestCase):
    def test_letter_analytics_mock_transport(self):
        from app.services import posthog_capture

        key=self.ready()
        first,second=uuid4(),uuid4()
        endpoint=f'/daily/letters/{key}'
        settings={'POSTHOG_ENVIRONMENT':'validation','POSTHOG_ID_KEY':'test-key',
                  'POSTHOG_HOST':'https://us.i.posthog.com','POSTHOG_PROJECT_TOKEN':'test-token'}
        with patch.dict(os.environ,settings),patch.object(posthog_capture,'urlopen') as send:
            self.client.get('/daily/letters?view=archive')
            self.client.get(endpoint)
            send.assert_not_called()
            self.uid=2
            self.assertEqual(self.client.post(f'{endpoint}/view?visit_id={first}&source=today').status_code,404)
            send.assert_not_called()
            self.uid=1
            self.assertEqual(self.client.post(f'{endpoint}/view?visit_id={first}&source=today').status_code,200)
            for _ in range(2):
                self.assertEqual(self.client.post(f'{endpoint}/save').status_code,200)
            self.assertEqual(self.client.post(f'{endpoint}/view?visit_id={second}&source=archive').status_code,200)
        events=[json.loads(call.args[0].data) for call in send.call_args_list]
        self.assertEqual([item['event'] for item in events],
                         ['letter_detail_viewed','letter_saved','letter_detail_viewed'])
        initial,saved,revisit=[item['properties'] for item in events]
        self.assertEqual(initial['letter_id'],saved['letter_id'])
        self.assertEqual(initial['letter_id'],revisit['letter_id'])
        self.assertNotEqual(initial['visit_id'],revisit['visit_id'])
        self.assertNotEqual(initial['visit_id'],str(first))
        self.assertTrue(initial['first_view'])
        self.assertFalse(revisit['first_view'])
        self.assertEqual((initial['source'],revisit['source']),('today','archive'))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.engine=create_engine('sqlite:///'+str(Path(self.tmp.name)/'daily.db'),connect_args={'check_same_thread':False,'timeout':15})
        Base.metadata.create_all(self.engine)
        self.now=datetime(2026,11,3,22)
        with Session(self.engine) as db:
            for uid in (1,2):db.add(User(id=uid,username=f's{uid}',email=f's{uid}@example.org',nickname='합성',hashed_password='unused',registered_at=datetime(2026,11,3)))
            db.commit()
        migrate_daily_schema(self.engine,datetime(2026,11,3))
        self.clock=patch.object(svc,'get_kst_now',side_effect=lambda:self.now).start()
        patch.object(api,'get_kst_now',side_effect=lambda:self.now).start()
        patch.object(writing,'get_kst_now',side_effect=lambda:self.now).start()
        self.ai=Mock(side_effect=lambda kind,source,*args:{'summary':'합성 요약','key_sentence':'합성 핵심','keywords':['합성']} if kind=='summary' else {'encourage_content':'합성님, 애쓰셨어요.'})
        self.index=Mock();self.search=Mock(return_value=[])
        app=FastAPI();app.include_router(api.router)
        def database():
            with Session(self.engine) as db:yield db
        self.uid=1
        app.dependency_overrides[get_db]=database
        app.dependency_overrides[get_current_user]=lambda:User(id=self.uid)
        self.client=TestClient(app)

    def tearDown(self):
        patch.stopall();self.engine.dispose();self.tmp.cleanup()

    def message(self,when=None,uid=1):
        with Session(self.engine) as db:
            row=ChatMessage(user_id=uid,session_id='synthetic',role='user',message='합성 대화',timestamp=when or self.now-timedelta(minutes=1),turn=1)
            db.add(row);db.commit();return row.id

    def run_all(self):
        for key in svc.dispatch(self.engine,self.now):
            svc.run_job(self.engine,key,generate=self.ai,search=self.search,index=self.index,now=self.now)

    def count(self,model):
        with Session(self.engine) as db:return db.query(model).count()

    def test_expired_trial_keeps_memory_summary_but_no_new_letter(self):
        with Session(self.engine) as db:
            db.get(User,1).registered_at=datetime(2026,10,1);db.commit()
        self.message();self.run_all()
        self.assertEqual(self.count(SummaryRange),1)
        self.assertEqual(self.count(EncouragementReport),0)
        self.assertEqual([call.args[0] for call in self.ai.call_args_list],['summary'])
        self.assertEqual(self.client.get('/daily/inbox').json()['state'],'unavailable')

    def test_letter_generated_during_access_change_is_not_delivered(self):
        original=self.ai.side_effect
        def change_access(kind,*args):
            result=original(kind,*args)
            if kind=='letter':
                with Session(self.engine) as db:
                    db.get(User,1).registered_at=datetime(2026,10,1);db.commit()
            return result
        self.ai.side_effect=change_access
        self.message();self.run_all()
        self.assertEqual(self.count(SummaryRange),1)
        self.assertEqual(self.count(EncouragementReport),0)
        self.assertEqual(self.count(ResultNotice),0)
        with Session(self.engine) as db:
            self.assertTrue(db.get(DailyJob,'1:2026-11-03:encouragement').letter_done)

    def test_no_dialogue_then_late_no_letter_but_midnight_summary(self):
        self.run_all();self.message(self.now+timedelta(minutes=1));self.now+=timedelta(hours=1);self.run_all()
        self.assertEqual(self.ai.call_count,0)
        self.now=datetime(2026,11,4);self.run_all()
        self.assertEqual(self.count(SummaryRange),1);self.assertEqual(self.count(EncouragementReport),0)

    def test_pre_and_midnight_partition_and_idempotence(self):
        first=self.message();self.run_all();self.run_all()
        extra=self.message(datetime(2026,11,3,23,59,55))
        self.message(datetime(2026,11,4,0,0,5))
        self.now=datetime(2026,11,4,0,0,10);self.run_all();self.run_all()
        with Session(self.engine) as db:
            rows=db.query(SummaryRange).filter_by(user_id=1).all()
            self.assertEqual({r.phase:r.source_ids for r in rows},{'encouragement':[first],'midnight':[extra]})
        self.assertEqual(self.ai.call_count,3);self.assertEqual(self.count(EncouragementReport),1)
        self.assertEqual(self.count(ResultNotice),1)

    def test_no_extra_one_summary(self):
        self.message();self.run_all();self.now=datetime(2026,11,4);self.run_all()
        self.assertEqual(self.count(SummaryRange),1)

    def test_discarded_writing_source_is_included(self):
        mid=self.message();self.run_all()
        with Session(self.engine) as db:self.assertIn(mid,db.query(SummaryRange).first().source_ids)

    def test_search_failure_fallback_without_regeneration(self):
        self.message();self.search.side_effect=RuntimeError('synthetic');self.run_all();self.run_all()
        self.assertEqual(self.ai.call_count,2);self.assertEqual(self.count(EncouragementReport),1)

    def test_summary_failure_letter_once_then_recover_next_day(self):
        self.message();good=self.ai.side_effect
        self.ai.side_effect=lambda kind,*args:(_ for _ in ()).throw(RuntimeError()) if kind=='summary' else good(kind,*args)
        self.run_all();self.assertEqual(self.count(EncouragementReport),1)
        self.ai.side_effect=good;self.now=datetime(2026,11,4,0,1);self.run_all()
        self.assertEqual(self.count(EncouragementReport),1);self.assertEqual(self.count(SummaryRange),1)

    def test_index_failure_does_not_repeat_ai(self):
        self.message();self.index.side_effect=RuntimeError();self.run_all()
        self.index.side_effect=None;self.now+=timedelta(minutes=3);self.run_all()
        self.assertEqual(self.ai.call_count,2);self.assertEqual(self.count(SummaryRange),1)

    def test_summary_save_retry_uses_checkpointed_result(self):
        self.message()
        with patch.object(svc,'save_summary',side_effect=RuntimeError()):self.run_all()
        self.assertEqual(self.count(SummaryRange),0)
        self.now+=timedelta(minutes=3);self.run_all()
        self.assertEqual(self.ai.call_count,2);self.assertEqual(self.count(SummaryRange),1)

    def test_generation_finishing_after_midnight_does_not_deliver(self):
        self.message();self.now=datetime(2026,11,3,23,59,59)
        keys=svc.dispatch(self.engine,self.now);good=self.ai.side_effect
        def crossing(kind,*args):
            result=good(kind,*args)
            if kind=='letter':self.now=datetime(2026,11,4,0,0,1)
            return result
        self.ai.side_effect=crossing
        svc.run_job(self.engine,keys[0],generate=self.ai,search=self.search,index=self.index)
        self.assertEqual(self.count(EncouragementReport),0)

    def test_concurrent_writing_start_reuses_one(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids=list(pool.map(lambda _:writing.start_writing(self.engine,1).id,range(2)))
        self.assertEqual(ids[0],ids[1])

    def test_existing_saved_diary_reopened_instead_of_new_writing_diary(self):
        with Session(self.engine) as db:
            db.add(DiaryReport(user_id=1,content='기존 합성',timestamp=self.now,state='saved'));db.commit()
        row=writing.start_writing(self.engine,1)
        self.assertIsNotNone(row.diary_id);self.assertEqual(self.count(DiaryReport),1)

    def test_publication_retry_keeps_single_notice(self):
        self.ready();publisher=Mock(side_effect=RuntimeError())
        svc.publish_notices(self.engine,publisher)
        publisher.side_effect=None;svc.publish_notices(self.engine,publisher);svc.publish_notices(self.engine,publisher)
        self.assertEqual(publisher.call_count,2);self.assertEqual(self.count(ResultNotice),1)

    def test_letter_failure_retry_same_day_summary_once(self):
        self.message();good=self.ai.side_effect
        self.ai.side_effect=lambda kind,*args:(_ for _ in ()).throw(RuntimeError()) if kind=='letter' else good(kind,*args)
        self.run_all();self.ai.side_effect=good;self.now+=timedelta(minutes=3);self.run_all()
        self.assertEqual(self.count(SummaryRange),1);self.assertEqual(self.count(EncouragementReport),1)

    def test_no_previous_day_letter_after_failure(self):
        self.message();good=self.ai.side_effect
        self.ai.side_effect=lambda kind,*args:(_ for _ in ()).throw(RuntimeError()) if kind=='letter' else good(kind,*args)
        self.run_all();self.ai.side_effect=good;self.now=datetime(2026,11,4);self.run_all()
        self.assertEqual(self.count(EncouragementReport),0)

    def test_concurrent_workers_single_generation(self):
        self.message();keys=svc.dispatch(self.engine,self.now)
        def run():svc.run_job(self.engine,keys[0],generate=self.ai,search=self.search,index=self.index,now=self.now)
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:run(),range(2)))
        self.assertEqual(self.ai.call_count,2);self.assertEqual(self.count(EncouragementReport),1)

    def test_time_change_past_immediate_and_after_received_tomorrow(self):
        self.message(datetime(2026,11,3,20,59));self.now=datetime(2026,11,3,21)
        response=self.client.put('/daily/settings',json={'hour':20})
        self.assertEqual(response.status_code,200);self.run_all()
        result=self.client.put('/daily/settings',json={'hour':19}).json()
        self.assertEqual(result['effective_date'],'2026-11-04');self.assertEqual(result['today_hour'],20)

    def test_settings_validate_and_account_isolation(self):
        self.assertEqual(self.client.put('/daily/settings',json={'hour':24}).status_code,422)
        self.assertEqual(self.client.put('/daily/settings',json={'hour':True}).status_code,422)
        self.client.put('/daily/settings',json={'hour':18});self.uid=2
        self.assertEqual(self.client.get('/daily/settings').json()['hour'],22)

    def ready(self):
        self.message();self.run_all()
        return self.client.get('/daily/inbox').json()['letter']['id']

    def test_save_same_row_both_then_midnight_archive(self):
        key=self.ready();self.client.post(f'/daily/letters/{key}/save');self.client.post(f'/daily/letters/{key}/save')
        self.assertEqual(len(self.client.get('/daily/letters?view=archive').json()['items']),1)
        self.assertIsNotNone(self.client.get('/daily/inbox').json()['letter'])
        self.now=datetime(2026,11,4)
        self.assertIsNone(self.client.get('/daily/inbox').json()['letter'])
        self.assertEqual(self.count(EncouragementReport),1)

    def test_unseen_previous_day_separate_access_and_discard(self):
        key=self.ready();self.now=datetime(2026,11,4)
        self.assertIsNone(self.client.get('/daily/inbox').json()['letter'])
        self.assertEqual(self.client.get('/daily/letters').json()['items'][0]['id'],key)
        self.assertEqual(self.client.get(f'/daily/letters/{key}').status_code,200)
        with patch.object(api,'capture_writing_event') as capture:
            for _ in range(2):
                self.assertEqual(self.client.post(f'/daily/letters/{key}/discard').status_code,200)
            capture.assert_called_once_with('letter_discarded',1,key,self.now,letter_id=key)
        self.assertEqual(self.client.get('/daily/letters').json()['items'],[])
        self.assertEqual(self.client.get(f'/daily/letters/{key}').status_code,404)

    def test_archive_delete_and_ownership(self):
        key=self.ready();self.uid=2
        self.assertEqual(self.client.get(f'/daily/letters/{key}').status_code,404)
        self.assertEqual(self.client.post(f'/daily/letters/{key}/save').status_code,404)
        self.uid=1;self.client.post(f'/daily/letters/{key}/save');self.client.post(f'/daily/letters/{key}/archive-delete')
        self.assertEqual(self.client.get('/daily/letters?view=archive').json()['items'],[])
        self.now=datetime(2026,11,4)
        self.assertEqual(self.client.get(f'/daily/letters/{key}').status_code,404)
        self.assertEqual(self.client.post(f'/daily/letters/{key}/view').status_code,404)
        self.assertEqual(self.client.post(f'/daily/letters/{key}/archive-delete').status_code,200)

    def test_notice_snapshot_does_not_ack_new_arrival(self):
        self.ready();old=self.client.get('/daily/notices').json()
        with Session(self.engine) as db:db.add(ResultNotice(user_id=1,kind='weekly',result_id=3,created_at=self.now));db.commit()
        self.client.post('/daily/notices/seen',json={'through_id':old['through_id']})
        self.assertEqual(self.client.get('/daily/notices').json()['count'],1)
        self.assertEqual(self.client.get('/daily/notices').json()['count'],1)
        self.uid=2;self.assertEqual(self.client.get('/daily/notices').json()['count'],0)

    def test_db_day_guard_and_discard_rewrite(self):
        with Session(self.engine) as db:
            db.add(DiaryReport(user_id=1,content='합성',timestamp=self.now,state='saved'));db.commit()
        with Session(self.engine) as db:
            db.add(DiaryReport(user_id=1,content='중복',timestamp=self.now+timedelta(seconds=1)))
            with self.assertRaises(Exception):db.commit()
        with Session(self.engine) as db:
            db.query(DiaryReport).update({'state':'discarded'});db.commit()
            db.add(DiaryReport(user_id=1,content='새작성',timestamp=self.now+timedelta(seconds=2)));db.commit()

    def test_migration_idempotent_and_no_source_mutation(self):
        self.message();migrate_daily_schema(self.engine,self.now);migrate_daily_schema(self.engine,self.now)
        self.assertEqual(self.count(ChatMessage),1)
        with Session(self.engine) as db:self.assertEqual(db.get(DailyActivation,1).activated_at,datetime(2026,11,3))


if __name__=='__main__':unittest.main()
