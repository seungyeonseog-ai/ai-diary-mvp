"""UI 조정 검증: 독립 DB/합성 AI/실제 제품 템플릿. 원본 DB·색인 미접근."""
import os
os.environ['SECRET_KEY'] = 'isolated-ui-polish-test'
os.environ['OPENAI_API_KEY'] = 'test-only-no-network'
os.environ.pop('SPACE_LIVE_AI', None)
from tests.browser import space_server as fixture
from app.api.routers import daily_router
from app.core.daily_migration import migrate_daily_schema
from app.core.access_migration import migrate_access_schema
from app.utils.time_utils import get_kst_now

app = fixture.app
migrate_access_schema(fixture.engine)
migrate_daily_schema(fixture.engine, get_kst_now())
app.include_router(daily_router.router)
