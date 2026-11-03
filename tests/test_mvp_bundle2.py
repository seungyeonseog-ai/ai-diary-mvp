"""M06/M07: 실제 SQLite·라우터·저장 서비스, 합성 AI/알림. 운영 DB 사용 없음."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'bundle2-test-only-secret'
os.environ['OPENAI_API_KEY'] = 'test-only-no-network'

import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from app.core.connection import Base, get_db
from app.models.db.user_model import User
from app.models.db.study_model import DiaryAnalysisReport, WeeklyAnalysisReport
from app.api.dependencies.auth_dependencies import get_current_user
from app.api.routers import study_router as study
from app.services import weekly_analysis_service as weekly
from app.repositories.weekly_analysis_repository import (
    WeeklyAnalysisRepository, SOURCE_IDS_KEY, SourceBatchConflict)
from app.tasks import diary_analysis_event as task


class Bundle2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='diary-bundle2-')
        path = (Path(self.temp.name) / 'isolated.db').as_posix()
        self.engine = create_engine('sqlite:///' + path,
                                   connect_args={'check_same_thread': False, 'timeout': 10})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.sessions()
        self.db.add_all([User(id=i, username=f'owner{i}', email=f'u{i}@example.org',
                             nickname='synthetic', hashed_password='unused') for i in (1, 2)])
        self.db.commit()
        self.add_days()
        self.uid = 1
        app = FastAPI()
        app.include_router(study.router)
        def isolated_db():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = isolated_db
        app.dependency_overrides[get_current_user] = lambda: User(id=self.uid)
        self.client = TestClient(app)
        self.ai = patch.object(weekly, 'call_gpt', side_effect=[
            json.dumps({'trend': '합성 경향'}),
            json.dumps({'main_themes': ['합성 키워드'], 'insights': '합성 인사이트'}),
            json.dumps({'overall_assessment': '합성 평가'})
        ]).start()
        self.followup = patch.object(weekly.WeeklyAnalysisService, '_run_followup').start()

    def tearDown(self):
        patch.stopall()
        self.client.close()
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def add_days(self, owner=1, count=8, skip=3, offset=0, same_time=False):
        base = datetime(2026, 9, 1, 12)
        for i in range(count):
            day = base if same_time else base + timedelta(days=i + offset)
            self.db.add(DiaryAnalysisReport(user_id=owner,
                emotions=['기쁨'], scores=[0.5], keywords=['합성'], keyword_descriptions=['합성'],
                summary=f'SOURCE_{owner}_{i + offset}', date_str=day.strftime('%Y-%m-%d'),
                timestamp=day, is_used_in_weekly=(i == skip)))
        self.db.commit()

    def generate(self):
        return weekly.WeeklyAnalysisService(self.db).analyze_weekly_data(1)

    def counts(self):
        with self.sessions() as db:
            return (db.query(WeeklyAnalysisReport).count(),
                    db.query(DiaryAnalysisReport).filter_by(user_id=1, is_used_in_weekly=False).count())

    def original_ids(self):
        with self.sessions() as db:
            return [row.report_id for row in WeeklyAnalysisRepository(db).get_unused_weekly_reports(1)]

    def legacy(self, dates=None):
        row = WeeklyAnalysisReport(user_id=1, week_start_date=datetime(2026, 9, 1, 12),
            week_end_date=datetime(2026, 9, 8, 12),
            used_dates=dates if dates is not None else ['2026-09-01', '2026-09-02', '2026-09-03',
                '2026-09-05', '2026-09-06', '2026-09-07', '2026-09-08'],
            emotion_trend_result={}, keyword_pattern_result={}, comprehensive_pattern_result={})
        self.db.add(row)
        self.db.commit()
        return row

    def test_new_result_api_returns_exact_seven_sources_not_date_range_eight(self):
        expected = self.original_ids()
        self.add_days(owner=2)
        row = self.generate()
        self.assertIsNotNone(row)
        self.assertEqual(row.comprehensive_pattern_result[SOURCE_IDS_KEY], expected)
        self.assertIsInstance(row.used_dates, list)
        response = self.client.get(f'/study/seven-day-report/{row.analysis_id}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([d['id'] for d in response.json()['diary_analyses']], expected)
        self.assertEqual(self.counts(), (1, 0))
        prompts = repr(self.ai.call_args_list)
        self.assertNotIn('SOURCE_1_3', prompts)  # 중간의 이미 사용한 날은 분석에도 포함 안 됨.
        self.assertNotIn('SOURCE_2_', prompts)
        self.assertEqual(self.ai.call_count, 3)
        self.followup.assert_called_once_with(1, row.analysis_id)

    def test_new_provenance_ignores_later_same_date_duplicate(self):
        row = self.generate()
        expected = row.comprehensive_pattern_result[SOURCE_IDS_KEY]
        self.add_days(count=1, skip=-1)
        response = self.client.get(f'/study/seven-day-report/{row.analysis_id}')
        self.assertEqual([d['id'] for d in response.json()['diary_analyses']], expected)

    def test_legacy_native_list_and_json_string_exclude_interspersed_used_day(self):
        row = self.legacy()
        for stored in (row.used_dates, json.dumps(row.used_dates)):
            row.used_dates = stored
            self.db.commit()
            response = self.client.get(f'/study/seven-day-report/{row.analysis_id}')
            self.assertEqual(response.status_code, 200)
            ids = [d['id'] for d in response.json()['diary_analyses']]
            self.assertEqual(ids, self.original_ids())

    def test_legacy_ambiguous_duplicate_is_409_instead_of_guessing(self):
        row = self.legacy()
        self.add_days(count=1, skip=-1)
        self.assertEqual(self.client.get(f'/study/seven-day-report/{row.analysis_id}').status_code, 409)

    def test_missing_source_is_409_and_foreign_owner_is_404(self):
        row = self.generate()
        self.uid = 2
        self.assertEqual(self.client.get(f'/study/seven-day-report/{row.analysis_id}').status_code, 404)
        self.uid = 1
        with self.sessions() as db:
            source = db.get(DiaryAnalysisReport, row.comprehensive_pattern_result[SOURCE_IDS_KEY][0])
            source.user_id = 2  # 합성 손상: 원본이 다른 계정이면 조회에 섞지 않는다.
            db.commit()
        self.assertEqual(self.client.get(f'/study/seven-day-report/{row.analysis_id}').status_code, 409)

    def test_invalid_legacy_metadata_never_falls_back_to_date_range(self):
        row = self.legacy()
        for value in ('invalid json', [], None, {'dates': []}):
            row.used_dates = value
            self.db.commit()
            self.assertEqual(self.client.get(f'/study/seven-day-report/{row.analysis_id}').status_code, 409)

    def test_ai_failure_saves_nothing_and_keeps_sources_unused(self):
        self.ai.side_effect = RuntimeError('SYNTHETIC_PRIVATE_ERROR')
        with self.assertLogs(weekly.logger, level='ERROR') as logs:
            self.assertIsNone(self.generate())
        self.assertNotIn('SYNTHETIC_PRIVATE_ERROR', '\n'.join(logs.output))
        self.assertEqual(self.counts(), (0, 7))
        self.followup.assert_not_called()

    def test_failure_after_source_update_rolls_back_all_seven(self):
        with patch.object(WeeklyAnalysisRepository, '_add_weekly_analysis', side_effect=RuntimeError('synthetic')):
            self.assertIsNone(self.generate())
        self.assertEqual(self.counts(), (0, 7))
        self.followup.assert_not_called()

    def test_commit_failure_rolls_back_insert_and_source_flags(self):
        def fail_commit(_):
            raise RuntimeError('synthetic commit failure')
        event.listen(Session, 'before_commit', fail_commit)
        try:
            self.assertIsNone(self.generate())
        finally:
            event.remove(Session, 'before_commit', fail_commit)
        self.assertEqual(self.counts(), (0, 7))
        self.followup.assert_not_called()

    def test_invalid_ai_json_does_not_consume_sources(self):
        self.ai.side_effect = ['not JSON']
        self.assertIsNone(self.generate())
        self.assertEqual(self.counts(), (0, 7))

    def test_partial_claim_or_foreign_source_rolls_back_claimed_subset(self):
        ids = self.original_ids()
        with self.sessions() as db:
            db.get(DiaryAnalysisReport, ids[0]).is_used_in_weekly = True
            db.commit()
        with self.assertRaises(SourceBatchConflict):
            WeeklyAnalysisRepository(self.db).save_weekly_analysis(1, datetime(2026, 9, 1),
                datetime(2026, 9, 8), ['x'] * 7, {}, {}, {}, ids)
        self.assertEqual(self.counts(), (0, 6))
        self.add_days(owner=2, count=1, skip=-1)
        with self.sessions() as db:
            foreign_id = db.query(DiaryAnalysisReport).filter_by(user_id=2).first().report_id
        with self.assertRaises(SourceBatchConflict):
            WeeklyAnalysisRepository(self.db).save_weekly_analysis(1, datetime(2026, 9, 1),
                datetime(2026, 9, 8), ['x'] * 7, {}, {}, {}, ids[1:] + [foreign_id])
        self.assertEqual(self.counts(), (0, 6))

    def test_repeat_after_success_does_not_call_ai_or_save_again(self):
        self.assertIsNotNone(self.generate())
        self.assertIsNone(self.generate())
        self.assertEqual(self.ai.call_count, 3)
        self.assertEqual(self.counts(), (1, 0))

    def test_fewer_than_seven_sources_does_not_call_ai(self):
        with self.sessions() as db:
            row = db.get(DiaryAnalysisReport, self.original_ids()[0])
            row.is_used_in_weekly = True
            db.commit()
        self.assertIsNone(self.generate())
        self.ai.assert_not_called()
        self.assertEqual(self.counts(), (0, 6))

    def test_same_timestamp_batches_use_id_order_and_both_batches_are_allowed(self):
        # 날짜를 7종류로 강제하지 않고 기존 '미사용 분석 7건' 정책을 유지한다.
        self.db.query(DiaryAnalysisReport).delete()
        self.db.commit()
        self.add_days(count=14, skip=-1, same_time=True)
        self.ai.side_effect = ['{}'] * 6
        first = self.generate()
        second = self.generate()
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        first_ids = first.comprehensive_pattern_result[SOURCE_IDS_KEY]
        second_ids = second.comprehensive_pattern_result[SOURCE_IDS_KEY]
        self.assertEqual(first_ids, sorted(first_ids))
        self.assertEqual(second_ids, sorted(second_ids))
        self.assertFalse(set(first_ids) & set(second_ids))
        for row, ids in ((first, first_ids), (second, second_ids)):
            response = self.client.get(f'/study/seven-day-report/{row.analysis_id}')
            self.assertEqual([d['id'] for d in response.json()['diary_analyses']], ids)
        self.assertEqual(self.counts(), (2, 0))

    def test_legacy_partial_save_is_preserved_and_not_regenerated(self):
        self.legacy()
        self.assertIsNone(self.generate())
        self.ai.assert_not_called()
        self.assertEqual(self.counts(), (1, 7))

    def test_ai_wait_does_not_keep_its_read_session_or_block_other_writer(self):
        def inspect_before_ai(_):
            self.assertEqual(self.engine.pool.checkedout(), 0)
            with self.sessions() as db:
                db.add(User(username='parallel', email='parallel@example.org', hashed_password='unused', nickname='synthetic'))
                db.commit()
            return {}
        with patch.object(weekly.WeeklyAnalysisService, '_analyze_emotion_trend', side_effect=inspect_before_ai):
            self.ai.side_effect = ['{}', '{}']
            self.assertIsNotNone(self.generate())

    def test_two_real_threads_save_only_one_result_for_the_same_batch(self):
        barrier = threading.Barrier(2)
        def hold_both_after_selection(_):
            barrier.wait(timeout=10)
            return {}
        def run():
            with self.sessions() as db:
                return weekly.WeeklyAnalysisService(db).analyze_weekly_data(1)
        with patch.object(weekly.WeeklyAnalysisService, '_analyze_emotion_trend', side_effect=hold_both_after_selection), \
             patch.object(weekly.WeeklyAnalysisService, '_analyze_keyword_pattern', return_value={}), \
             patch.object(weekly.WeeklyAnalysisService, '_analyze_comprehensive', return_value={}):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: run(), range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(self.counts(), (1, 0))
        self.assertEqual(self.followup.call_count, 1)

    def test_event_notification_observes_commit_and_retry_keeps_saved_result(self):
        def notify(channel, message):
            self.assertEqual(channel, 'user_1_report')
            self.assertEqual(self.counts(), (1, 0))
            self.assertEqual(json.loads(message)['analysis_id'], 1)
            raise RuntimeError('synthetic notification outage')
        with self.assertRaises(RuntimeError):
            task.run_weekly_analysis_and_notify(self.db, 1, notify)
        publish = Mock()
        self.assertIsNone(task.run_weekly_analysis_and_notify(self.db, 1, publish))
        publish.assert_not_called()
        self.assertEqual(self.counts(), (1, 0))

    def test_retired_event_task_does_not_generate_old_batch(self):
        with patch.object(task,'run_weekly_analysis_and_notify') as old:
            self.assertEqual(task.check_weekly_analysis_after_diary_save.run(1)['status'],'replaced_by_weekly_cycles')
            old.assert_not_called()

    def test_periodic_delegates_to_new_cycle_dispatch(self):
        path=Path(__file__).resolve().parents[1]/'app/services/celery_app.py'
        node=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='check_weekly_analysis_conditions_periodic')
        node.decorator_list=[]
        dispatch=Mock();scope={'daily_diary_analysis':dispatch}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
        scope[node.name]();dispatch.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
