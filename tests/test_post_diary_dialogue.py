"""묶음3: 초안/저장/기존 일기를 유지하는 추가 대화."""
import unittest
from datetime import datetime,timedelta
from sqlalchemy.orm import Session
from tests import test_writing_flow as support
from app.models.db.study_model import DiaryReport


class PostDiaryTests(unittest.TestCase):
    def setUp(self):self.f=support.WritingFlowTests();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def quota(self,writing):return self.f.client.get('/writing/'+writing).json()['quota']
    def detail(self,diary):return self.f.client.get('/writing/diaries/'+str(diary)).json()

    def test_extra_before_and_after_save_keeps_same_diary(self):
        writing,diary=self.f.draft();before=self.detail(diary)
        self.f.message(writing,'초안 후 합성 이야기','after-draft');self.f.generate(writing,key='after-draft')
        self.assertEqual(self.detail(diary),before)
        self.f.client.post(f'/writing/diaries/{diary}/save',json={'version':1});saved=self.detail(diary)
        self.f.message(writing,'저장 후 합성 이야기','after-save');self.f.generate(writing,key='after-save')
        self.assertEqual(self.detail(diary),saved)
        q=self.quota(writing);self.assertEqual((q['base_remaining'],q['extra_used'],q['extra_remaining']),(0,2,0))
        self.assertEqual(self.f.client.post(f'/writing/{writing}/messages',json={'request_id':'denied','message':'합성'}).status_code,409)
        self.assertEqual(self.f.start(),writing)

    def test_failed_extra_after_diary_retries_without_new_diary(self):
        writing,diary=self.f.draft();before=self.detail(diary)
        self.f.message(writing,key='extra');self.f.ai.side_effect=RuntimeError('synthetic outage')
        self.f.generate(writing,key='extra',status=503)
        self.assertEqual(self.quota(writing)['extra_used'],0)
        self.f.ai.side_effect=None;self.f.ai.return_value={'bubbles':['합성 답변']}
        self.f.generate(writing,key='extra');self.f.generate(writing,key='extra')
        self.assertEqual(self.quota(writing)['extra_used'],1)
        self.assertEqual(self.detail(diary),before)

    def test_free_account_keeps_result_but_cannot_add_after_diary(self):
        self.f.now+=timedelta(days=8)
        writing,diary=self.f.draft()
        self.assertEqual(self.quota(writing)['extra_remaining'],0)
        self.assertEqual(self.f.client.post(f'/writing/{writing}/messages',json={'request_id':'no-right','message':'합성'}).status_code,409)
        self.assertEqual(self.detail(diary)['state'],'draft')

    def test_legacy_today_diary_does_not_grant_another_base(self):
        with Session(self.f.engine) as db:
            row=DiaryReport(user_id=1,title='기존 합성',content='기존 합성 본문',source_type='ai',state='saved',version=1,timestamp=self.f.now,updated_at=self.f.now)
            db.add(row);db.commit();diary=row.diary_id
        writing=self.f.start();q=self.quota(writing)
        self.assertEqual((q['base_used'],q['base_remaining'],q['extra_remaining']),(0,0,2))
        before=self.detail(diary);self.f.message(writing,key='legacy-extra');self.f.generate(writing,key='legacy-extra')
        self.assertEqual(self.quota(writing)['extra_used'],1);self.assertEqual(self.detail(diary),before)

    def test_cached_diary_replay_does_not_generate_or_reset_usage(self):
        writing,diary=self.f.draft();calls=self.f.ai.call_count
        result=self.f.generate(writing,'diary','diary1')
        self.assertEqual(result['result']['diary_id'],diary);self.assertEqual(self.f.ai.call_count,calls)
        self.assertEqual(self.quota(writing)['base_remaining'],0)
        self.f.generate(writing,'diary','different-diary',status=409)

    def test_other_account_cannot_continue_or_read_diary(self):
        writing,diary=self.f.draft();self.f.owner=2
        self.assertEqual(self.f.client.post(f'/writing/{writing}/messages',json={'request_id':'foreign','message':'합성'}).status_code,404)
        self.assertEqual(self.f.client.get(f'/writing/diaries/{diary}').status_code,404)


if __name__=='__main__':unittest.main()
