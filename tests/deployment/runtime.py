"""제품 main/DB/Redis/Chroma를 사용하고 유료 AI 생성만 합성으로 대체한다."""
import asyncio
import os
if (os.environ.get("ENVIRONMENT") != "validation" or os.environ.get("DEPLOYMENT_VALIDATION") != "1"
        or os.environ.get("OPENAI_API_KEY") != "synthetic-docker-validation-no-real-key"
        or os.environ.get("DATABASE_URL") != "sqlite:////data/app.db"):
    raise RuntimeError("Validation runtime must use an isolated synthetic deployment")
# 누락된 합성 경계도 실제 외부 AI로 연결되지 못하게 한다.
os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:9/blocked"
from app.main import app
from app.services.celery_app import celery
from app.services import writing_stream, daily_ai
from app.api.routers import writing_router
from app.api.dependencies.auth_dependencies import get_current_user
from app.core.connection import engine
from app.models.db.user_model import User
from app.models.db.study_model import DiaryReport, EncouragementReport
from app.models.db.writing_model import DiaryPhoto
from app.models.db.daily_model import DailyJob
from app.models.db.access_model import AccountAccess
from app.utils.time_utils import get_kst_now
from datetime import timedelta
from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
gate=asyncio.Event()
gate.set()


async def chunks(source, memories):
    await asyncio.sleep(.2)
    yield '{"bubbles":["검증용 첫 말풍선이에요.",'
    await gate.wait()
    await asyncio.sleep(2)
    yield '"검증용 두 번째 말풍선이에요."]}'


async def generate(kind, source):
    await asyncio.sleep(.3)
    if kind == "diary":
        return {"title":"배포 검증 기록","body":"합성 검증: 작은 일을 마치고 산책했다. 오늘의 기록을 저장했다."}
    return {"bubbles":["검증용 첫 말풍선이에요.","검증용 두 번째 말풍선이에요."]}


def daily_generate(kind, source, nickname="", memories=None):
    if kind == "summary":
        return {"summary":"합성 검증: 산책하며 작은 성취를 돌아보았다.","key_sentence":"산책하며 하루를 돌아보았다.","keywords":["산책","성취"]}
    return {"encourage_content":nickname+"님, 오늘의 작은 수고를 기억해요.\n격리 Docker 예약 전달 검증용 편지입니다."}


REAL_AI = os.environ.get("DEPLOYMENT_VALIDATION_REAL_AI") == "1"
if REAL_AI:
    # 실제 키는 예산 프록시에만 둔다. 앱은 제한된 프록시로만 요청한다.
    os.environ["OPENAI_BASE_URL"] = "http://ai-budget:8090/v1"
else:
    writing_stream.lamp_chunks = chunks
    writing_router.generate = generate
    daily_ai.generate = daily_generate


@app.post("/validation/gate/{action}")
async def control_gate(action: str, user: User = Depends(get_current_user)):
    if action == "close":gate.clear()
    else:gate.set()
    return {"open":gate.is_set()}


@app.get("/validation/evidence")
def evidence(user: User = Depends(get_current_user)):
    import chromadb
    from app.config.settings import settings
    from app.services.sparse_service import SparseIndexService
    with Session(engine) as db:
        jobs=db.query(DailyJob).filter_by(user_id=user.id).all()
        result={"diaries":db.query(DiaryReport).filter_by(user_id=user.id,state="saved").count(),
            "photos":db.query(DiaryPhoto).filter_by(user_id=user.id).count(),
            "letters":db.query(EncouragementReport).filter_by(user_id=user.id).count(),
            "jobs":[{"phase":j.phase,"state":j.state,"error_type":j.error_type} for j in jobs]}
    sparse=SparseIndexService()
    try:result["fts_rows"]=sparse.conn.execute("SELECT count(*) FROM docs_fts WHERE user_id=?",(user.id,)).fetchone()[0]
    finally:sparse.conn.close()
    client=chromadb.HttpClient(host=settings.chroma_host,port=settings.chroma_port)
    try:
        collection=client.get_collection("chat_system")
        result["dense_rows"]=len(collection.get(where={"user_id":user.id},include=[])["ids"])
    except chromadb.errors.NotFoundError:
        result["dense_rows"]=0
    result["ai_mode"]="real-budget-proxy" if REAL_AI else "synthetic-external-blocked"
    return result


@app.post("/validation/expire")
def expire(user: User = Depends(get_current_user)):
    with Session(engine) as db:
        row=db.get(AccountAccess,user.id)
        row.trial_started_at=get_kst_now()-timedelta(days=8)
        row.trial_expires_at=get_kst_now()-timedelta(days=1)
        db.commit()
    return {"expired":True}
