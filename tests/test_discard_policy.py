"""묶음4: 기본만 복구·추가 사용 유지·원문 보존·늦은 완료 차단."""
import unittest
from datetime import timedelta
from sqlalchemy.orm import Session
from tests import test_writing_flow as support
from app.services import writing_service as service
from app.models.db.chat_message_model import ChatMessage
from app.models.db.writing_model import WritingOperation

class DiscardPolicyTests(unittest.TestCase):
 def setUp(self):self.f=support.WritingFlowTests();self.f.setUp()
 def tearDown(self):self.f.tearDown()
 def q(self,w):return self.f.client.get('/writing/'+w).json()['quota']
 def test_zero_one_two_used_extras_survive_diary_discard(self):
  for used in range(3):
   if used:self.tearDown();self.setUp()
   w,d=self.f.draft()
   for i in range(used):self.f.message(w,key=f'extra{i}');self.f.generate(w,key=f'extra{i}')
   with Session(self.f.engine) as db:count=db.query(ChatMessage).count()
   r=self.f.client.delete(f'/writing/diaries/{d}');self.assertTrue(r.json()['can_rewrite_today'])
   self.assertEqual(self.f.client.get(f'/writing/diaries/{d}').status_code,404)
   old=self.f.client.get('/writing/'+w).json();self.assertEqual(old['messages'],[]);self.assertIsNone(old['diary'])
   new=self.f.start();self.assertNotEqual(w,new);q=self.q(new)
   self.assertEqual((q['base_remaining'],q['extra_used'],q['extra_remaining']),(1,used,2-used))
   with Session(self.f.engine) as db:self.assertEqual(db.query(ChatMessage).count(),count)
 def test_pending_extra_cancelled_and_late_completion_denied(self):
  w,d=self.f.draft();self.f.message(w,key='pending');op,_=service.claim_operation(self.f.engine,1,w,'pending','lamp')
  self.f.client.delete(f'/writing/diaries/{d}')
  with self.assertRaises(service.WritingError):service.complete_operation(self.f.engine,1,op.id,op.lease_token,{'bubbles':['늦은 합성 답변']})
  with Session(self.f.engine) as db:
   row=db.get(WritingOperation,op.id);self.assertEqual(row.state,'cancelled');self.assertIsNone(row.lease_token)
  q=self.q(self.f.start());self.assertEqual((q['base_remaining'],q['extra_used'],q['extra_reserved']),(1,0,0))
 def test_expired_free_account_can_repeat_with_unique_requests(self):
  self.f.now+=timedelta(days=8)
  for i in range(3):
   w=self.f.start();self.f.message(w,key=f'free{i}');self.f.generate(w,key=f'free{i}')
   self.f.generate(w,'diary',f'diary{i}');d=self.f.client.get('/writing/'+w).json()['diary']['id']
   self.f.client.delete(f'/writing/diaries/{d}')
   q=self.q(self.f.start());self.assertEqual((q['base_remaining'],q['extra_remaining']),(1,0))
 def test_other_account_cannot_discard(self):
  w,d=self.f.draft();self.f.owner=2
  self.assertEqual(self.f.client.delete(f'/writing/diaries/{d}').status_code,404)
  self.f.owner=1;self.assertEqual(self.f.client.get(f'/writing/diaries/{d}').status_code,200)
 def test_old_date_discard_does_not_replace_today(self):
  w,d=self.f.draft();self.f.now+=timedelta(days=1);today=self.f.start()
  r=self.f.client.delete(f'/writing/diaries/{d}');self.assertFalse(r.json()['can_rewrite_today'])
  self.assertEqual(self.f.start(),today);self.assertEqual(self.q(today)['base_remaining'],1)

if __name__=='__main__':unittest.main()
