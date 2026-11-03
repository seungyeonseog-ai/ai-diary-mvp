"""M03/M04/M05: 실제 라우터·격리 DB의 상태/복원/한국 날짜/계정 격리."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'bundle3-test-only-secret'
os.environ['OPENAI_API_KEY'] = 'test-only-no-network'

from datetime import datetime, timedelta
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.connection import Base, get_db
from app.api.dependencies.auth_dependencies import get_current_user
from app.api.routers import study_router as study
from app.services import study_state_service as state
from app.models.db.user_model import User
from app.models.db.session_log import SessionLog
from app.models.db.chat_message_model import ChatMessage
from app.models.db.study_model import DiaryReport, EncouragementReport, WeeklyAnalysisReport, DiaryAnalysisReport


class Bundle3Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread':False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.sessions()
        self.now = datetime(2026, 10, 29, 12)
        self.uid = 1
        self.db.add_all([User(id=i, username=f'owner{i}', email=f'u{i}@example.org',
            nickname='synthetic', hashed_password='unused') for i in (1,2)])
        self.db.add_all([SessionLog(user_id=i, session_id=f'bundle3-{i}', start_time=self.now) for i in (1,2)])
        self.db.commit()
        app = FastAPI()
        app.include_router(study.router)
        def isolated_db():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = isolated_db
        app.dependency_overrides[get_current_user] = lambda: User(id=self.uid)
        self.app = app
        self.client = TestClient(app)
        self.clock = patch.object(state, 'get_kst_now', side_effect=lambda:self.now).start()
        patch.object(study, 'get_kst_now', side_effect=lambda:self.now).start()
        self.redis = Mock()
        patch.object(study.redis, 'Redis', return_value=self.redis).start()

    def tearDown(self):
        patch.stopall()
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def words(self, count, owner=1, when=None, role='user'):
        self.db.add(ChatMessage(user_id=owner, session_id=f'bundle3-{owner}',
            message='합성 ' * count, role=role, timestamp=when or self.now, turn=1))
        self.db.commit()

    def letter(self, owner=1, when=None, content='SYNTHETIC_PRIVATE_LETTER'):
        row = EncouragementReport(user_id=owner, timestamp=when or self.now,
            encourage_content=content, music=[], singer=[])
        self.db.add(row)
        self.db.commit()
        return row

    def weekly(self, owner=1, when=None):
        dates = [(self.now-timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7,0,-1)]
        for day in dates:
            self.db.add(DiaryAnalysisReport(user_id=owner, date_str=day,
                timestamp=datetime.fromisoformat(day), emotions=['기쁨'], scores=[0.5],
                keywords=['합성'], keyword_descriptions=['합성'], summary='SYNTHETIC_PRIVATE_SUMMARY',
                is_used_in_weekly=True))
        row = WeeklyAnalysisReport(user_id=owner, timestamp=when or self.now,
            week_start_date=datetime.fromisoformat(dates[0]), week_end_date=datetime.fromisoformat(dates[-1]),
            used_dates=dates, emotion_trend_result={}, keyword_pattern_result={},
            comprehensive_pattern_result={'overall_assessment':'합성'})
        self.db.add(row)
        self.db.commit()
        return row

    def status(self):
        response = self.client.get('/study/status')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_empty_cache_or_notification_is_irrelevant_to_saved_state(self):
        letter = self.letter()
        weekly = self.weekly()
        data = self.status()
        self.assertEqual(data['encouragement'], {'state':'ready','id':letter.encouragement_id,'date':'2026-10-29'})
        self.assertEqual(data['weekly'], {'state':'ready','analysis_id':weekly.analysis_id})
        self.redis.publish.assert_not_called()  # 단순 상태 조회가 읽음 처리하지 않음.
        self.assertNotIn('SYNTHETIC_PRIVATE', json.dumps(data))

    def test_today_result_is_available_in_condition_api(self):
        row = self.letter()
        data = self.client.get('/study/encourage/check-condition').json()
        self.assertTrue(data['available'])
        self.assertEqual(data['id'], row.encouragement_id)

    def test_old_letter_is_not_today_and_is_not_returned(self):
        self.letter(when=self.now-timedelta(days=1))
        self.assertEqual(self.status()['encouragement']['state'], 'waiting_time')
        self.assertEqual(self.client.get('/study/encourage').status_code, 404)
        self.redis.publish.assert_not_called()

    def test_read_returns_server_date_id_and_kst_timestamp(self):
        row = self.letter()
        response = self.client.get('/study/encourage')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['id'], row.encouragement_id)
        self.assertEqual(data['date'], data['server_date'])
        self.assertTrue(data['timestamp'].endswith('+09:00'))
        channel, message = self.redis.publish.call_args.args
        self.assertEqual(channel, 'user_1_encourage')
        self.assertEqual(json.loads(message)['date'], '2026-10-29')

    def test_ack_failure_keeps_saved_letter_readable(self):
        self.letter()
        self.redis.publish.side_effect = RuntimeError('synthetic outage')
        self.assertEqual(self.client.get('/study/encourage').status_code, 200)
        self.assertEqual(self.status()['encouragement']['state'], 'ready')

    def test_account_isolation_for_status_letter_and_latest_weekly(self):
        self.letter(owner=2)
        self.weekly(owner=2)
        self.assertIsNone(self.status()['encouragement']['id'])
        self.assertIsNone(self.status()['weekly']['analysis_id'])
        self.assertEqual(self.client.get('/study/encourage').status_code, 404)
        self.assertEqual(self.client.get('/study/weekly/latest').status_code, 404)

    def test_new_routes_and_encouragement_require_auth(self):
        self.app.dependency_overrides.pop(get_current_user)
        for path in ('/study/status','/study/weekly/latest','/study/encourage','/study/encourage/check-condition'):
            self.assertEqual(self.client.get(path).status_code, 401)

    def test_generation_thresholds_and_time_remain_distinct(self):
        self.assertEqual(self.status()['encouragement']['state'], 'waiting_time')
        self.words(55)
        data = self.status()
        self.assertTrue(data['diary']['available'])
        self.assertEqual(data['encouragement']['state'], 'waiting_time')
        self.words(45)
        self.now = self.now.replace(hour=9)
        self.assertEqual(self.status()['encouragement']['state'], 'waiting_time')
        self.now = self.now.replace(hour=22)
        self.assertEqual(self.status()['encouragement']['state'], 'pending')

    def test_other_owner_assistant_and_yesterday_words_do_not_unlock_today(self):
        self.words(100, owner=2)
        self.words(100, role='assistant')
        self.words(100, when=self.now-timedelta(days=1))
        self.assertFalse(self.status()['diary']['available'])

    def test_kst_midnight_ends_old_letter_and_old_diary_state(self):
        self.now = self.now.replace(hour=23,minute=59)
        self.letter()
        self.db.add(DiaryReport(user_id=1, content='synthetic', source_type='ai', timestamp=self.now))
        self.db.commit()
        self.assertEqual(self.status()['diary']['state'], 'saved')
        self.now = datetime(2026,10,30,0,0)
        data = self.status()
        self.assertEqual(data['server_date'], '2026-10-30')
        self.assertEqual(data['diary']['state'], 'insufficient')
        self.assertIsNone(data['encouragement']['id'])

    def test_latest_weekly_can_be_discovered_without_knowing_an_id(self):
        own = self.weekly()
        self.weekly(owner=2, when=self.now+timedelta(minutes=1))
        response = self.client.get('/study/weekly/latest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['weekly_analysis']['id'], own.analysis_id)
        self.assertEqual(len(response.json()['diary_analyses']),7)

    def test_pending_weekly_is_seven_unused_reports(self):
        row = self.weekly()
        self.db.delete(row)
        self.db.query(DiaryAnalysisReport).update({'is_used_in_weekly':False})
        self.db.commit()
        self.assertEqual(self.status()['weekly']['state'], 'pending')

    def test_latest_today_letter_uses_stable_id_order(self):
        self.letter(content='first')
        second = self.letter(content='second')
        self.assertEqual(self.client.get('/study/encourage').json()['id'], second.encouragement_id)

    def test_status_failure_has_generic_message_and_no_raw_sql_log(self):
        broken = Mock()
        broken.query.side_effect = RuntimeError('SYNTHETIC_PRIVATE_SQL')
        self.app.dependency_overrides[get_db] = lambda:broken
        with self.assertLogs(study.logger,level='ERROR') as logs:
            response = self.client.get('/study/status')
        self.assertEqual(response.status_code,500)
        self.assertNotIn('SYNTHETIC_PRIVATE_SQL', response.text+' '.join(logs.output))

    def test_websocket_relay_preserves_reset_and_letter_date_metadata(self):
        from app.services.websocket_service import WebSocketService
        values = [({'type':'diary_reset','date':'2026-10-29'},'user_1_diary'),
                  ({'type':'encourage_unavailable','date':'2026-10-29','result_id':9},'user_1_encourage'),
                  ({'type':'encourage_availalbe','date':'2026-10-29','result_id':10},'user_1_encourage')]
        async def messages():
            for data, channel in values:
                yield {'type':'message','data':json.dumps(data).encode(),'channel':channel.encode()}
        pubsub = Mock(subscribe=AsyncMock(),aclose=AsyncMock(),listen=messages)
        relay = WebSocketService.__new__(WebSocketService)
        relay.redis_client = Mock(pubsub=Mock(return_value=pubsub))
        relay.is_websocket_connected = AsyncMock(return_value=True)
        relay.send_notification = AsyncMock()
        asyncio.run(relay.subscribe_to_notifications(1, object()))
        forwarded = [call.args[1] for call in relay.send_notification.call_args_list]
        self.assertEqual([value['date'] for value in forwarded], ['2026-10-29']*3)
        self.assertEqual(forwarded[1]['result_id'],9)
        self.assertEqual(forwarded[2]['type'],'encourage_available')
        pubsub.aclose.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
