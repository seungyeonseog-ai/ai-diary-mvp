"""M12: 미제공 경로 무호출 및 응원 저장 계약 (격리)."""
import os
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['SECRET_KEY']='features-isolated'
os.environ['OPENAI_API_KEY']='test-placeholder'
import unittest, json, ast, sys
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.connection import Base, get_db
from app.models.db.session_log import SessionLog
from app.models.db.user_model import User
from app.models.db.study_model import EncouragementReport
from app.api.dependencies.auth_dependencies import get_current_user
from app.api.routers import constellation
from app.config.settings import settings
from app.services import encourage_diary_service as encourage
from app.services.weekly_analysis_service import WeeklyAnalysisService
from app.services.report_service import ReportService
from app.tasks import similar_pattern_event_check as task

class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.off=patch.multiple(settings,music_recommendations_enabled=False, upper_reports_enabled=False)
        self.off.start()
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions=sessionmaker(bind=self.engine)
        self.db=self.sessions()
        self.db.add(User(id=1,username='u',email='u@example.test',nickname='합성',hashed_password='unused'))
        self.db.commit()
    def tearDown(self):
        self.db.close();self.engine.dispose();self.off.stop()
    def test_letter_only_request_ignores_unwanted_music_fields(self):
        for response in ({'encourage_content':'합성 응원'}, {'encourage_content':'합성 응원','music':['unwanted'],'singer':['unwanted']}):
            with patch.object(encourage,'call_gpt',return_value=json.dumps(response)) as ai, patch.object(encourage.redis,'Redis') as redis:
                svc=encourage.EncourageDiaryService(self.db)
                svc.today_chat_repo=Mock()
                svc.today_chat_repo.get_today_user_chat_content_and_tokens.return_value=('synthetic chat',100)
                result=svc.create_encouragement(1)
                self.assertTrue(result)
                self.assertEqual(result.music,[]);self.assertEqual(result.singer,[])
                prompt=ai.call_args.args[0]
                self.assertNotIn('music',str(prompt));self.assertNotIn('singer',str(prompt));self.assertNotIn('노래',str(prompt))
                self.assertEqual(redis.return_value.publish.call_count,1)
        self.assertEqual(self.db.query(EncouragementReport).count(),2)
    def test_legacy_music_branch_is_preserved_but_explicitly_enabled(self):
        with patch.object(settings,'music_recommendations_enabled',True),patch.object(encourage,'call_gpt',return_value=json.dumps({'encourage_content':'합성','music':['song'],'singer':['artist']})) as ai,patch.object(encourage.redis,'Redis'):
            svc=encourage.EncourageDiaryService(self.db);svc.today_chat_repo=Mock()
            svc.today_chat_repo.get_today_user_chat_content_and_tokens.return_value=('synthetic',100)
            self.assertEqual(svc.create_encouragement(1).music,['song'])
            self.assertIn('music',str(ai.call_args.args))
    def test_weekly_followup_does_not_import_or_construct_search(self):
        with patch.dict(sys.modules, {'app.services.weekly_similar_flow_service':None}):
            WeeklyAnalysisService(self.db)._run_followup(1,1)
    def test_queued_task_returns_before_db_api_write_or_publish(self):
        with patch.object(task,'SessionLocal') as db,patch.object(task,'ReportService') as service,patch.object(task.redis_client,'publish') as publish:
            self.assertEqual(task.check_similar_pattern_analysis_ready.run(1),{'status':'feature_disabled'})
            db.assert_not_called();service.assert_not_called();publish.assert_not_called()
    def test_direct_report_service_returns_before_query_or_api(self):
        with patch('app.services.report_service.call_gpt') as ai:
            service=ReportService(Mock())
            service.similar_pattern_repo=Mock()
            self.assertIsNone(service.generate_comprehensive_report(1,1))
            service.similar_pattern_repo.get_by_id_and_user_id.assert_not_called();ai.assert_not_called()
    def test_flow_entry_returns_before_search_initialization(self):
        # 실제 run/__init__ 본문을 분리하여 대형 검색 라이브러리 로딩 없이 검사한다.
        from pathlib import Path
        tree=ast.parse(Path('app/services/weekly_similar_flow_service.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
        methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('__init__','run')]
        env={'settings':settings,'SimilarPatternService':Mock(),'get_db':Mock(),'Dict':dict}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='Flow',bases=[],keywords=[],body=methods,decorator_list=[])],type_ignores=[])),'flow','exec'),env)
        self.assertEqual(env['Flow']().run(1,1)['reason'],'feature_disabled')
        env['SimilarPatternService'].assert_not_called();env['get_db'].assert_not_called()
    def test_read_api_disabled_still_requires_authentication(self):
        app=FastAPI();app.include_router(constellation.router)
        app.dependency_overrides[get_db]=lambda:self.db
        with TestClient(app) as client:
            self.assertEqual(client.get('/personality-report/1').status_code,401)
            app.dependency_overrides[get_current_user]=lambda:User(id=1)
            self.assertEqual(client.get('/personality-report/1').status_code,404)

if __name__=='__main__':unittest.main()
