"""묶음2: 성공 사용량·처리 중 예약·재시도. 기존 작성 fixture의 격리 DB만 사용한다."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import patch
from sqlalchemy.orm import Session
from tests import test_writing_flow as support
from app.services import writing_service as service
from app.models.db.writing_model import WritingOperation


class UsagePolicyTests(unittest.TestCase):
    def setUp(self):
        self.f=support.WritingFlowTests()
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def quota(self,writing):
        return self.f.client.get('/writing/'+writing).json()['quota']

    def fail_ai(self):
        self.f.ai.side_effect=RuntimeError('synthetic outage')

    def restore_ai(self):
        self.f.ai.side_effect=None
        self.f.ai.return_value={'bubbles':['합성 검증 답변']}

    def basic(self):
        writing=self.f.start();self.f.message(writing);self.f.generate(writing)
        return writing

    def test_basic_failure_releases_reservation_and_retry_charges_once(self):
        writing=self.f.start();self.f.message(writing);self.fail_ai()
        self.f.generate(writing,status=503)
        q=self.quota(writing)
        self.assertEqual((q['base_used'],q['base_reserved'],q['base_remaining']),(0,0,1))
        self.restore_ai();self.f.generate(writing);self.f.generate(writing)
        q=self.quota(writing)
        self.assertEqual((q['base_used'],q['base_reserved'],q['base_remaining']),(1,0,0))
        self.assertEqual(self.f.ai.call_count,2)

    def test_extra_failure_and_idempotent_retry(self):
        writing=self.basic();self.f.message(writing,key='extra');self.fail_ai()
        self.f.generate(writing,key='retry-extra',status=503)
        q=self.quota(writing)
        self.assertEqual((q['extra_used'],q['extra_reserved'],q['extra_remaining']),(0,0,2))
        self.restore_ai();self.f.generate(writing,key='retry-extra');self.f.generate(writing,key='retry-extra')
        q=self.quota(writing)
        self.assertEqual((q['extra_used'],q['extra_reserved'],q['extra_remaining']),(1,0,1))
        self.assertEqual(self.f.ai.call_count,3)

    def test_pending_reserves_but_does_not_count_as_success(self):
        writing=self.basic();self.f.message(writing,key='extra')
        op,_=service.claim_operation(self.f.engine,1,writing,'held','lamp')
        q=self.quota(writing)
        self.assertEqual((q['extra_used'],q['extra_reserved'],q['extra_remaining']),(0,1,1))
        self.f.generate(writing,key='held',status=409)
        self.f.generate(writing,key='different',status=409)
        service.fail_operation(self.f.engine,1,op.id,op.lease_token)
        q=self.quota(writing)
        self.assertEqual((q['extra_used'],q['extra_reserved'],q['extra_remaining']),(0,0,2))

    def test_checkpointed_result_save_retry_does_not_generate_again(self):
        writing=self.basic();self.f.message(writing,key='extra')
        with patch.object(service,'complete_operation',side_effect=RuntimeError('synthetic persistence outage')):
            self.f.generate(writing,key='save-retry',status=503)
        self.assertEqual(self.quota(writing)['extra_used'],0)
        calls=self.f.ai.call_count
        self.f.generate(writing,key='save-retry');self.f.generate(writing,key='save-retry')
        self.assertEqual(self.f.ai.call_count,calls)
        self.assertEqual(self.quota(writing)['extra_used'],1)

    def test_concurrent_claim_has_one_reservation_and_one_completion(self):
        writing=self.f.start();self.f.message(writing)
        def claim(_):
            try:return service.claim_operation(self.f.engine,1,writing,'race','lamp')[0]
            except service.WritingError as error:return error.status
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,range(2)))
        self.assertEqual(sum(value==409 for value in results),1)
        op=next(value for value in results if value!=409)
        q=self.quota(writing)
        self.assertEqual((q['base_used'],q['base_reserved'],q['base_remaining']),(0,1,0))
        service.complete_operation(self.f.engine,1,op.id,op.lease_token,{'bubbles':['합성 답변']})
        self.f.generate(writing,key='race')
        with Session(self.f.engine) as db:self.assertEqual(db.query(WritingOperation).count(),1)
        self.assertEqual(self.quota(writing)['base_used'],1)

    def test_expired_lease_reuses_operation_and_rejects_old_token(self):
        writing=self.f.start();self.f.message(writing)
        old,_=service.claim_operation(self.f.engine,1,writing,'lease','lamp')
        self.f.now+=timedelta(minutes=6)
        new,_=service.claim_operation(self.f.engine,1,writing,'lease','lamp')
        self.assertEqual(old.id,new.id);self.assertNotEqual(old.lease_token,new.lease_token)
        with self.assertRaises(service.WritingError):
            service.complete_operation(self.f.engine,1,old.id,old.lease_token,{'bubbles':['늦은 합성 답변']})
        service.complete_operation(self.f.engine,1,new.id,new.lease_token,{'bubbles':['합성 답변']})
        self.assertEqual((self.quota(writing)['base_used'],self.quota(writing)['base_reserved']),(1,0))

    def test_daily_usage_is_shared_across_writings_and_isolated_by_account(self):
        first=self.basic();self.f.message(first,key='extra');self.f.generate(first,key='extra')
        service.discard_writing(self.f.engine,1,first);self.f.now+=timedelta(seconds=1)
        second=self.f.start();q=self.quota(second)
        self.assertEqual((q['base_remaining'],q['extra_used'],q['extra_remaining']),(1,1,1))
        self.f.owner=2;other=self.f.start();q=self.quota(other)
        self.assertEqual((q['base_remaining'],q['extra_used'],q['extra_remaining']),(1,0,2))
        self.assertEqual(self.f.client.get('/writing/'+second).status_code,404)

    def test_failed_base_retry_after_another_success_uses_extra(self):
        writing=self.f.start();self.f.message(writing);self.fail_ai()
        self.f.generate(writing,key='old',status=503)
        self.restore_ai();self.f.message(writing,key='new');self.f.generate(writing,key='new')
        self.f.generate(writing,key='old')
        q=self.quota(writing)
        self.assertEqual((q['base_used'],q['extra_used']),(1,1))

    def test_failed_retry_cannot_bypass_exhausted_daily_extra(self):
        writing=self.basic();self.f.message(writing,key='failed');self.fail_ai()
        self.f.generate(writing,key='failed',status=503);self.restore_ai()
        for key in ('one','two'):
            self.f.message(writing,key=key);self.f.generate(writing,key=key)
        calls=self.f.ai.call_count
        self.f.generate(writing,key='failed',status=409)
        self.assertEqual(self.f.ai.call_count,calls)
        self.assertEqual((self.quota(writing)['extra_used'],self.quota(writing)['extra_remaining']),(2,0))

    def test_midnight_rejects_old_completion_without_using_new_day(self):
        self.f.now=datetime(2026,11,2,23,59,50)
        writing=self.f.start();self.f.message(writing)
        op,_=service.claim_operation(self.f.engine,1,writing,'midnight','lamp')
        service.checkpoint_result(self.f.engine,1,op.id,op.lease_token,{'bubbles':['합성 답변']})
        self.f.now=datetime(2026,11,3)
        with self.assertRaises(service.WritingError):
            service.complete_operation(self.f.engine,1,op.id,op.lease_token,{'bubbles':['합성 답변']})
        service.fail_operation(self.f.engine,1,op.id,op.lease_token)
        today=self.f.start();q=self.quota(today)
        self.assertEqual((q['base_remaining'],q['extra_used'],q['extra_remaining']),(1,0,2))
        self.f.generate(writing,key='midnight',status=409)
        self.assertEqual(self.f.ai.call_count,0)

    def test_cancelled_pending_does_not_consume_daily_extra(self):
        writing=self.basic();self.f.message(writing,key='extra')
        service.claim_operation(self.f.engine,1,writing,'cancel','lamp')
        service.discard_writing(self.f.engine,1,writing)
        self.f.now+=timedelta(seconds=1);today=self.f.start();q=self.quota(today)
        self.assertEqual((q['base_remaining'],q['extra_used'],q['extra_reserved'],q['extra_remaining']),(1,0,0,2))

    def test_diary_generation_and_save_do_not_charge_dialogue(self):
        writing,diary=self.f.draft();before=self.quota(writing)
        self.f.client.post(f'/writing/diaries/{diary}/save',json={'version':1})
        after=self.quota(writing)
        for key in ('base_used','extra_used','extra_reserved'):
            self.assertEqual(before[key],after[key])

    def test_old_day_pending_reservation_does_not_reduce_today(self):
        writing=self.f.start();self.f.message(writing)
        service.claim_operation(self.f.engine,1,writing,'old-day','lamp')
        self.f.now+=timedelta(days=1);today=self.f.start();q=self.quota(today)
        self.assertEqual((q['base_used'],q['base_reserved'],q['base_remaining'],q['extra_reserved']),(0,0,1,0))


if __name__=='__main__':unittest.main()
