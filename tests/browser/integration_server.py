"""8번 통합 검증: 새 격리 DB, 제품 라우터/화면, 명시적 고정 시각.

localhost 검증용이다. 운영 main에는 연결하지 않는다. AI/검색/Redis는
합성 대체하며 기존 사용자 DB와 인덱스에 쓰지 않는다.
"""
import os
if os.environ.get('SPACE_LIVE_AI'):
    raise RuntimeError('통합 합성 서버에서는 외부 AI 모드를 허용하지 않습니다.')

from datetime import datetime
from tests.browser import space_server as space
from app.api.routers import daily_router, library_router, writing_router
from app.services import daily_service, weekly_cycle_service, study_state_service, library_service, writing_service
from app.core.daily_migration import migrate_daily_schema
from app.core.weekly_migration import migrate_weekly_schema
from app.models.db.daily_model import DailyJob, LetterDelivery, ResultNotice
from app.models.db.weekly_cycle_model import AnalysisJob
from app.models.db.writing_model import SummaryRange
from app.models.db.study_model import DiaryAnalysisReport, WeeklyAnalysisReport
from sqlalchemy.orm import Session
from fastapi import HTTPException

app, engine = space.app, space.engine
clock = {'now': datetime(2026, 11, 3, 12)}
for module in (daily_router, writing_router, daily_service, weekly_cycle_service,
               study_state_service, library_service, writing_service):
    module.get_kst_now = lambda: clock['now']
migrate_daily_schema(engine, clock['now'])
migrate_weekly_schema(engine, clock['now'])
app.include_router(daily_router.router)
app.include_router(library_router.router)
generated = []
indexed = set()


def daily_generate(kind, source, nickname='', memories=None):
    generated.append({'kind': kind, 'source_chars': len(source)})
    if kind == 'summary':
        return {'summary': '합성 검증: 작은 일을 마치고 산책하며 마음을 돌아보았다.',
                'key_sentence': '작은 일을 마쳤다.', 'keywords': ['정리', '산책']}
    return {'encourage_content': nickname + '님, 오늘의 작은 수고를 기억해요.\n'
            '합성 통합 검증용 편지입니다.\n잠시 쉬어가도 괜찮아요.'}


def weekly_generate(kind, source):
    generated.append({'kind': kind})
    if kind == 'daily':
        return {'emotions': ['기쁨', '피곤'], 'scores': [.6, -.2], 'keywords': ['정리'],
                'keyword_descriptions': ['작은 일을 마쳤어요.'], 'summary': '합성 검증용 하루 분석입니다.'}
    if kind == 'emotion':
        return {'trend': '차분히 돌아본 한 주', 'dominant_emotion': '기쁨', 'recommendation': '쉬어가세요.'}
    if kind == 'keyword':
        return {'main_themes': ['정리'], 'recurring_patterns': ['작은 성취'], 'insights': '조금씩 나아갔어요.'}
    return {'overall_assessment': '합성 검증: 일상의 작은 성취를 돌아본 한 주입니다.'}


@app.post('/fixture/clock')
def set_clock(data: dict):
    value = datetime.fromisoformat(data['now'])
    if value.tzinfo or value < clock['now'] or value > datetime(2026, 11, 11):
        raise HTTPException(422, '격리 검사 기간 내에서 시각을 앞으로만 이동합니다.')
    clock['now'] = value
    return {'now': value.isoformat()}


@app.post('/fixture/tick')
def tick():
    for key in daily_service.dispatch(engine, clock['now']):
        daily_service.run_job(engine, key, generate=daily_generate, search=lambda *a: [],
            index=lambda uid, sid, day, result: indexed.add((uid, sid)), now=clock['now'])
    # 일일 결과가 저장된 뒤 주간 작업 등록까지 연결한다.
    for _ in range(2):
        for key in weekly_cycle_service.dispatch(engine, clock['now']):
            weekly_cycle_service.run(engine, key, generate=weekly_generate, now=clock['now'])
    return evidence()


@app.get('/fixture/integration-status')
def evidence():
    with Session(engine) as db:
        return {'now': clock['now'].isoformat(), 'external_ai_calls': 0,
                'database': str(space.fixture_path), 'generated': generated,
                'summary_ranges': [{'date': r.source_date, 'ids': r.source_ids} for r in db.query(SummaryRange)],
                'letters': db.query(LetterDelivery).count(), 'notices': db.query(ResultNotice).count(),
                'daily_analyses': db.query(DiaryAnalysisReport).count(),
                'weekly_analyses': db.query(WeeklyAnalysisReport).count(),
                'daily_jobs': [{'phase': r.phase, 'state': r.state} for r in db.query(DailyJob)],
                'analysis_jobs': [{'kind': r.kind, 'state': r.state} for r in db.query(AnalysisJob)],
                'indexed_ranges': len(indexed), **space.status()}
