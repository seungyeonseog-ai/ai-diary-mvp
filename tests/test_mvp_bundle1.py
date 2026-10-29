"""1묶음 회귀: 실제 라우터/메모리 DB. 외부 AI·사용자 DB 사용 없음."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'bundle1-test-only-secret'
os.environ['OPENAI_API_KEY'] = 'test-only-no-network'

import contextlib
from datetime import datetime
import io
import unittest
from unittest.mock import Mock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.connection import Base, get_db
from app.api.dependencies.auth_dependencies import get_current_user
from app.api.routers import study_router as study, auth_router as auth
from app.models.db.user_model import User
from app.models.db.study_model import WeeklyAnalysisReport, DiaryAnalysisReport

PRIVATE = 'SYNTHETIC_PRIVATE_MARKER_<img src=x onerror=alert(1)>'


class Bundle1Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool,
                                    connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([User(id=i, username=f'owner{i}', email=f'u{i}@example.org',
                             nickname='tester', hashed_password='unused') for i in (1, 2)])
            db.add(WeeklyAnalysisReport(analysis_id=1, user_id=1,
                week_start_date=datetime(2026, 10, 1), week_end_date=datetime(2026, 10, 7),
                used_dates=['2026-10-01'], emotion_trend_result={'trend': PRIVATE},
                keyword_pattern_result={'main_themes': [PRIVATE], 'insights': PRIVATE},
                comprehensive_pattern_result={'overall_assessment': PRIVATE}))
            db.add(DiaryAnalysisReport(user_id=1, date_str='2026-10-01',
                emotions=['기쁨'], scores=[1], keywords=[PRIVATE],
                keyword_descriptions=[PRIVATE], summary=PRIVATE))
            db.commit()
        self.uid = 1
        self.app = FastAPI()
        self.app.include_router(study.router)
        self.app.include_router(auth.router)
        def isolated_db():
            with self.sessions() as db:
                yield db
        self.app.dependency_overrides[get_db] = isolated_db
        self.app.dependency_overrides[auth.get_db] = isolated_db
        self.app.dependency_overrides[get_current_user] = lambda: User(id=self.uid)
        self.client = TestClient(self.app, base_url='https://diary.example.org')

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def test_weekly_read_preserves_content_but_logs_only_metadata(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertLogs(study.logger, level='INFO') as logs:
            response = self.client.get('/study/seven-day-report/1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['weekly_analysis']['emotion_trend']['trend'], PRIVATE)
        self.assertEqual(len(response.json()['diary_analyses']), 1)
        self.assertNotIn(PRIVATE, output.getvalue() + '\n'.join(logs.output))
        self.assertIn('analysis_id=1 user_id=1 count=1', '\n'.join(logs.output))

    def test_weekly_foreign_or_absent_404_without_content(self):
        self.uid = 2
        for rid in (1, 999):
            response = self.client.get(f'/study/seven-day-report/{rid}')
            self.assertEqual(response.status_code, 404)
            self.assertNotIn(PRIVATE, response.text)

    def test_weekly_requires_auth(self):
        self.app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.client.get('/study/seven-day-report/1').status_code, 401)

    def test_database_failure_hides_sql_parameters_from_logs_and_response(self):
        broken = Mock()
        broken.query.side_effect = StatementError('failed', 'SELECT private',
                                                   {'content': PRIVATE}, RuntimeError(PRIVATE))
        self.app.dependency_overrides[get_db] = lambda: broken
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertLogs(study.logger, level='ERROR') as logs:
            response = self.client.get('/study/seven-day-report/1')
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(PRIVATE, output.getvalue() + '\n'.join(logs.output) + response.text)
        self.assertIn('error_type=StatementError', '\n'.join(logs.output))

    def registration(self):
        return dict(username='newowner', email='new@example.org', password='Test12!ab',
                    nickname='합성 계정')

    def test_register_success_persists_hash_and_duplicate_does_not_insert(self):
        payload = self.registration()
        self.assertEqual(self.client.post('/register', json=payload).status_code, 200)
        self.assertEqual(self.client.post('/register', json=payload).status_code, 400)
        with self.sessions() as db:
            users = db.query(User).filter_by(username=payload['username']).all()
            self.assertEqual(len(users), 1)
            self.assertNotEqual(users[0].hashed_password, payload['password'])
        # 실제 로그인 검증 경로로 생성된 해시 확인 (테스트 DB에 로그인 기록만 생성).
        self.assertEqual(self.client.post('/login', json={k: payload[k] for k in ('username', 'password')}).status_code, 200)

    def test_register_validation_does_not_insert(self):
        for update in ({'email': 'invalid'}, {'password': 'abc'}, {'password': 'Ab111!'}):
            payload = {**self.registration(), **update}
            self.assertEqual(self.client.post('/register', json=payload).status_code, 422)
        with self.sessions() as db:
            self.assertEqual(db.query(User).count(), 2)


if __name__ == '__main__':
    unittest.main()
