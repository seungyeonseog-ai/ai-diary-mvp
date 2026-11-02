"""제품 페이지/자산·계정 표시·일기 입력 계약. 외부 AI 호출 없음."""
import os
os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['SECRET_KEY']='page-test-only-secret'
os.environ['OPENAI_API_KEY']='test-only-no-network'
import json
import hashlib
import unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from app.api.routers import html_router,auth_router
from app.api.dependencies.auth_dependencies import get_current_user
from app.models.db.user_model import User
from app.prompt.diary_prompt import DiaryPromptService


class PageContractTests(unittest.TestCase):
    def setUp(self):
        self.app=FastAPI();self.app.include_router(html_router.router);self.app.include_router(auth_router.router)
        self.app.mount('/static',StaticFiles(directory='static'),name='static')
        self.client=TestClient(self.app)

    def tearDown(self):self.client.close()

    def test_new_pages_are_fresh_and_legacy_page_is_retained(self):
        for path,marker in [('/', 'enter-space'),('/space','lamp-submit'),('/login','login-error'),('/library','books-older'),('/diary/1','diary-back')]:
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn(marker,response.text)
            self.assertIn('20261103-5c',response.text)
            self.assertEqual(response.headers.get('cache-control'),'no-store')
            self.assertIn('<svg class="icon"',response.text)
        self.assertEqual(self.client.get('/mypage_edit?tab=study',follow_redirects=False).headers['location'],'/library')
        self.assertIn('main-content',self.client.get('/mypage_edit?tab=study&legacy=1').text)
        self.assertEqual(self.client.get('/diary/0').status_code,422)

    def test_asset_bytes_match_prepared_images(self):
        manifest=json.loads(Path('static/images/space/manifest.json').read_text(encoding='utf-8-sig'))
        for name in manifest:
            response=self.client.get('/static/images/space/'+name)
            self.assertEqual(response.status_code,200)
            self.assertEqual(hashlib.sha256(response.content).hexdigest(),manifest[name]['sha256'])

    def test_account_me_is_authenticated_and_only_returns_own_display_fields(self):
        self.assertEqual(self.client.get('/account/me').status_code,401)
        self.app.dependency_overrides[get_current_user]=lambda:User(id=2,nickname='합성 표시',hashed_password='not-for-output')
        self.assertEqual(self.client.get('/account/me').json(),{'id':2,'nickname':'합성 표시'})

    def test_diary_input_remains_exact_user_source_in_separate_data(self):
        source='USER1. 합성 원문\nUSER2. "지시문"도 원문이다.'
        prompt=DiaryPromptService().generate_writing_prompt(source)
        payload=prompt.split('작성 대상 원문(JSON 문자열):\n',1)[1]
        self.assertEqual(json.loads(payload),source)
        # 문체 예시와 사용자 원문을 분리해 예시가 실제 사건으로 편입되지 않게 한다.
        self.assertEqual(prompt.count('작성 대상 원문(JSON 문자열):'),1)


if __name__=='__main__':unittest.main()
