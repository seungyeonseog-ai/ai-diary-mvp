"""제품3탭/기존자료/오류를 합성 DB에서 검사. 유료AI 없음."""
from tests.browser.daily_server import app,engine,clock
from app.core.weekly_migration import migrate_weekly_schema
from app.models.db.study_model import DiaryAnalysisReport,WeeklyAnalysisReport
from app.models.db.daily_model import ResultNotice
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
from datetime import datetime
import os,sqlite3,json
from pathlib import Path

migrate_weekly_schema(engine)
app.router.routes=[r for r in app.router.routes if getattr(r,'path','')!='/study/weekly/latest']
from app.api.routers.study_router import get_latest_weekly_report
app.add_api_route('/study/weekly/latest',get_latest_weekly_report,methods=['GET'])
path=Path(os.environ['WEEKLY_AI_TEST_DB']).resolve(strict=True)
if not path.parent.name.startswith('weekly-ai-'):raise ValueError('격리 weekly-ai 자료만 허용')
with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as source,Session(engine) as db:
    ids=[]
    for row in source.execute('SELECT date_str,emotions,scores,keywords,keyword_descriptions,summary FROM diary_analysis_reports ORDER BY date_str'):
        report=DiaryAnalysisReport(user_id=1,date_str=row[0],timestamp=datetime.fromisoformat(row[0]),emotions=json.loads(row[1]),scores=json.loads(row[2]),keywords=json.loads(row[3]),keyword_descriptions=json.loads(row[4]),summary=row[5],is_used_in_weekly=True)
        db.add(report);db.flush();ids.append(report.report_id)
    results=source.execute('SELECT emotion_trend_result,keyword_pattern_result,comprehensive_pattern_result FROM weekly_analysis_reports').fetchone()
    overall=json.loads(results[2]);overall['_source_report_ids']=ids
    report=WeeklyAnalysisReport(user_id=1,week_start_date=datetime(2026,11,1),week_end_date=datetime(2026,11,7),used_dates=['2026-11-01','2026-11-03','2026-11-07'],emotion_trend_result=json.loads(results[0]),keyword_pattern_result=json.loads(results[1]),comprehensive_pattern_result=overall,timestamp=clock['now'])
    db.add(report);db.commit()

fault={'weekly':0}
@app.middleware('http')
async def weekly_fault(request,call_next):
    if request.url.path=='/study/weekly/latest' and fault['weekly']:
        fault['weekly']-=1;return JSONResponse({'detail':'검증용 주간 조회 오류예요.'},status_code=503)
    return await call_next(request)

@app.post('/fixture/weekly-error')
def error():fault['weekly']+=1;return {'ok':True}
