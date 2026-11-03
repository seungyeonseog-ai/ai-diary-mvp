from fastapi import FastAPI
from app.config.settings import settings
from app.api.routers.html_router import router as html_router
from app.api.routers.auth_router import router as register_router
from app.core.connection import Base, engine
from app.api.routers.chat_message_router import router as chat_router
from app.api.routers.chat_event_router import router as chat_event_router
from app.api.routers.websocket_router import router as websocket_router
from app.api.routers.study_router import router as study_router
from app.api.routers.constellation import router as constellation_router
from app.api.routers.writing_router import router as writing_router
from app.api.routers.library_router import router as library_router
from app.core.writing_migration import require_writing_schema
from app.core.access_migration import require_access_schema
from app.api.routers.access_router import router as access_router
import asyncio
from contextlib import suppress
from app.tasks.session_task_runner import session_checker_all_users_loop
import logging
from app.models.db.user_model import User  # ✅ 반드시 추가
from app.models.db.session_log import SessionLog 
from app.models.db.session_summary import SessionSummary
from app.models.db.study_model import DiaryAnalysisReport
from transformers import AutoTokenizer , AutoModelForCausalLM
import torch
import os
from pathlib import Path
#from app.services import endtime_event
# from app.services.celery_app import summarize_task
# 3분 세션 종료 요약 리스너는 날짜별 작업으로 대체했다.
from fastapi.staticfiles import StaticFiles  # 추가 필요
from app.api.routers.daily_router import router as daily_router
from app.core.daily_migration import require_daily_schema
from app.core.weekly_migration import require_weekly_schema
from app.models.db import daily_model




# 기존 핸들러 초기화
for h in logging.root.handlers[:]:
    logging.root.removeHandler(h)

# 루트 로거 레벨을 DEBUG로, 출력 포맷 지정
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)

# Uvicorn 내장 로거까지 DEBUG로 바꾸기
logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)




require_access_schema(engine)
Base.metadata.create_all(bind=engine) # 클래스 정의생성해서 테이블 만들기
require_writing_schema(engine)
require_daily_schema(engine)
require_weekly_schema(engine)


app = FastAPI()



# 🔽 이거 추가!
app.mount("/static", StaticFiles(directory="static"), name="static")



# 라우터 등록
app.include_router(register_router)
app.include_router(html_router)
app.include_router(chat_router)
app.include_router(chat_event_router)
app.include_router(websocket_router)
app.include_router(study_router)
app.include_router(constellation_router)
app.include_router(writing_router)
app.include_router(library_router)
app.include_router(daily_router)
app.include_router(access_router)


@app.on_event("startup")
async def startup_event():
    # 모델 로딩 제거 ✅

    # 세션 체크 백그라운드 실행
    print("🌀 전체 세션 체크 백그라운드 시작")
    # 예약/자정은 Celery Beat의 영속 날짜 작업으로 실행한다.
    app.state.session_checker = None


@app.on_event("shutdown")
async def shutdown_event():
    task = getattr(app.state, "session_checker", None)
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task



# main.py 하단
for route in app.routes:
    print("✅ Registered route:", route.path)




