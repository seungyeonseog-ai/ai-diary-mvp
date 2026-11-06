"""공개 정적 파일 정책과 5일 차트 실제 UI의 격리 검증 서버."""
import json
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session
from tests.browser.integration_server import app, engine, clock
from app.core.public_static import public_static
from app.models.db.access_model import AccountAccess
from app.models.db.study_model import DiaryAnalysisReport, WeeklyAnalysisReport
from app.repositories.weekly_analysis_repository import SOURCE_IDS_KEY

app.router.routes[:] = [r for r in app.router.routes if getattr(r, 'path', None) != '/static']
app.mount('/static', public_static(), name='static')
with Session(engine) as db:
    for row in db.query(AccountAccess):
        row.onboarding_completed_at = clock['now']
    # 별도 실AI 검증에서 만든 합성 결과만 사용한다. 없으면 빈 상태를 검증한다.
    path = Path('.local-check/five-day-ai-result.json')
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8'))
        if len(data.get('result', {})) == 3:
            ids = []
            for day in data['days']:
                row = DiaryAnalysisReport(user_id=1, date_str=day['date'], timestamp=datetime.fromisoformat(day['date']),
                    emotions=day['emotions'], scores=day['scores'], keywords=day['keywords'],
                    keyword_descriptions=day['keyword_descriptions'], summary=day['summary'], is_used_in_weekly=True)
                db.add(row); db.flush(); ids.append(row.report_id)
            result = data['result']
            db.add(WeeklyAnalysisReport(user_id=1, week_start_date=datetime(2026,11,3), week_end_date=datetime(2026,11,7),
                used_dates=[d['date'] for d in data['days']], emotion_trend_result=result['emotion'],
                keyword_pattern_result=result['keyword'], comprehensive_pattern_result={**result['comprehensive'], SOURCE_IDS_KEY:ids, '_schema_version':2}, timestamp=datetime(2026,11,7,23,51)))
    db.commit()
