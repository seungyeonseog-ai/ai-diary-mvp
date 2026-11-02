"""서재 조회/기존 일기 조작. 임시 DB와 합성 자료만 사용, AI 호출 없음."""
import os
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['SECRET_KEY']='library-test-only'
os.environ['OPENAI_API_KEY']='test-no-network'
import unittest,tempfile
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.connection import Base,get_db
from app.api.dependencies.auth_dependencies import get_current_user
from app.api.routers import library_router,writing_router
from app.services import library_service,writing_service
from app.models.db.user_model import User
from app.models.db.study_model import DiaryReport
from app.models.db.writing_model import Writing,DiaryPhoto
from app.models.db.chat_message_model import ChatMessage


class LibraryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.engine=create_engine('sqlite:///'+str(Path(self.temp.name)/'library.db'),connect_args={'check_same_thread':False})
  Base.metadata.create_all(self.engine);self.now=datetime(2026,11,2,23,59,55);self.owner=1
  with Session(self.engine) as db:
   db.add_all([User(id=i,username=f'synth{i}',email=f'synth{i}@example.org',nickname='합성',hashed_password='unused') for i in (1,2)])
   for index in range(12):db.add(DiaryReport(diary_id=index+1,user_id=1,title=f'합성 기록 {index+1}',content='합성 본문\n두번째 줄',timestamp=self.now-timedelta(days=index),state='saved'))
   db.add_all([DiaryReport(diary_id=20,user_id=1,title='',content='옛 형식',timestamp=datetime(2024,2,29,12)),
               DiaryReport(diary_id=21,user_id=2,title='다른 계정',content='격리 검증',timestamp=self.now),
               DiaryReport(diary_id=22,user_id=1,title='초안',state='draft',timestamp=self.now-timedelta(minutes=1)),
               DiaryReport(diary_id=23,user_id=1,title='폐기',state='discarded',timestamp=self.now-timedelta(minutes=2)),
               DiaryReport(diary_id=24,user_id=1,title='미래',state='saved',timestamp=self.now+timedelta(days=1))])
   db.add(ChatMessage(user_id=1,session_id='synthetic-source',role='user',message='합성 원본 보존',timestamp=self.now))
   db.commit()
  for module in (library_service,writing_service,writing_router):patch.object(module,'get_kst_now',side_effect=lambda:self.now).start()
  app=FastAPI();app.include_router(library_router.router);app.include_router(writing_router.router)
  def isolated():
   with Session(self.engine) as db:yield db
  app.dependency_overrides[get_db]=isolated;app.dependency_overrides[get_current_user]=lambda:User(id=self.owner)
  self.app=app;self.client=TestClient(app)
 def tearDown(self):
  patch.stopall();self.client.close();self.engine.dispose();self.temp.cleanup()
 def test_shelf_paging_and_account_isolation(self):
  first=self.client.get('/library-data/shelf').json();self.assertEqual(first['total'],13);self.assertEqual([b['id'] for b in first['books']],[1,2,3,4,5]);self.assertFalse(first['has_newer']);self.assertTrue(first['has_older'])
  last=self.client.get('/library-data/shelf?page=999').json();self.assertEqual(last['page'],3);self.assertEqual([b['state'] for b in last['books']],['saved']*3+['empty']*2)
  self.owner=2;other=self.client.get('/library-data/shelf').json();self.assertEqual(other['total'],1);self.assertEqual(other['books'][1],{'state':'future','date':'2026-11-03'})
  self.assertEqual(self.client.get('/writing/diaries/1').status_code,404)
 def test_empty_shelf_and_future_slots(self):
  self.owner=3;data=self.client.get('/library-data/shelf').json();self.assertEqual(data['total'],0);self.assertEqual(len(data['books']),5);self.assertEqual(data['books'][0]['date'],'2026-11-03');self.assertFalse(data['has_newer']);self.assertFalse(data['has_older'])
 def test_month_calendar_not_limited_by_list_page(self):
  data=self.client.get('/library-data/month?month=2026-10&page=2').json();self.assertEqual(data['total'],10);self.assertEqual(len(data['days']),10);self.assertEqual(len(data['items']),5);self.assertEqual(data['items'][0]['id'],8)
  self.assertEqual(self.client.get('/library-data/month').json()['month'],'2026-11')
 def test_leap_day_legacy_title_and_multiple_same_day(self):
  data=self.client.get('/library-data/month?month=2024-02').json();self.assertEqual(data['items'][0]['title'],'2월 29일의 기록');self.assertIn('2024-02-29',data['days'])
  with Session(self.engine) as db:db.add(DiaryReport(user_id=1,title='같은 날',timestamp=self.now-timedelta(seconds=1)));db.commit()
  self.assertEqual(len(self.client.get('/library-data/month').json()['days']['2026-11-02']),2)
 def test_invalid_and_future_month_and_page(self):
  for query in ('month=2026-13','month=0000-01','month=2026-12','month=9999-12','page=0','page=-1'):
   self.assertEqual(self.client.get('/library-data/month?'+query).status_code,422,query)
 def test_read_errors_safe_retry_and_auth_required(self):
  with patch.object(library_service,'shelf',side_effect=RuntimeError('internal synthetic detail')):
   response=self.client.get('/library-data/shelf');self.assertEqual(response.status_code,503);self.assertNotIn('internal',response.text)
  self.assertEqual(self.client.get('/library-data/shelf').status_code,200)
  del self.app.dependency_overrides[get_current_user]
  self.assertEqual(self.client.get('/library-data/shelf').status_code,401)
 def test_detail_read_creates_no_writing_and_edit_preserves_saved_state(self):
  before=self.client.get('/writing/diaries/3').json();self.assertEqual(before['server_date'],'2026-11-02')
  response=self.client.patch('/writing/diaries/3',json={'version':before['version'],'title':'변경한 제목','body':'수정한 본문'})
  self.assertEqual(response.status_code,200);self.assertEqual(response.json()['state'],'saved')
  self.assertEqual(self.client.patch('/writing/diaries/3',json={'version':before['version'],'title':'충돌','body':'충돌'}).status_code,409)
  with Session(self.engine) as db:self.assertEqual(db.query(Writing).count(),0);self.assertEqual(db.get(DiaryReport,3).timestamp.date().isoformat(),'2026-10-31')
 def test_past_delete_no_rewrite_today_delete_can_rewrite_source_retained(self):
  old=self.client.delete('/writing/diaries/3').json();self.assertFalse(old['can_rewrite_today']);self.assertEqual(self.client.get('/writing/diaries/3').status_code,404)
  self.assertFalse(self.client.delete('/writing/diaries/3').json()['can_rewrite_today'])
  self.assertTrue(self.client.delete('/writing/diaries/1').json()['can_rewrite_today'])
  with Session(self.engine) as db:self.assertEqual(db.query(ChatMessage).count(),1)
 def test_midnight_date_guard_and_owner_write_guard(self):
  self.now=datetime(2026,11,3,0,0,5);self.assertFalse(self.client.delete('/writing/diaries/1').json()['can_rewrite_today'])
  self.owner=2;self.assertEqual(self.client.delete('/writing/diaries/2').status_code,404)
 def test_photo_thumbnail_is_private_and_removed_on_discard(self):
  from tests.test_writing_flow import PNG
  response=self.client.post('/writing/diaries/3/photos?version=1&request_id=photo-1',content=PNG,headers={'content-type':'image/png'})
  self.assertEqual(response.status_code,200,response.text)
  item=next(i for i in self.client.get('/library-data/month?month=2026-10').json()['items'] if i['id']==3);url=item['photo_url'];self.assertTrue(url)
  photo=self.client.get(url);self.assertEqual(photo.content,PNG);self.assertEqual(photo.headers['cache-control'],'private, no-store')
  self.owner=2;self.assertEqual(self.client.get(url).status_code,404)
  self.owner=1;self.client.delete('/writing/diaries/3');self.assertEqual(self.client.get(url).status_code,404)
  with Session(self.engine) as db:self.assertEqual(db.query(DiaryPhoto).count(),0)

if __name__=='__main__':unittest.main()
