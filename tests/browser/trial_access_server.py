"""묶음1 분리본의 실제 HTTP/브라우저 검사. 별도 포트·DB·합성 AI 전용.

723e94c를 내보낸 디렉터리에 이 파일만 복사해 실행한다.
작업 트리의 후속 묶음 모델이 섞이면 시작을 거부한다.
"""
import os
from pathlib import Path
from datetime import datetime

if os.environ.get("SPACE_LIVE_AI"):
    raise RuntimeError("체험 브라우저 검사에서는 실제 AI 모드를 허용하지 않습니다.")
Path(".local-check").mkdir(exist_ok=True)
os.environ["SECRET_KEY"] = "isolated-trial-browser-test"
os.environ["OPENAI_API_KEY"] = "test-only-no-network"

from tests.browser import space_server as space
from app.api.routers import daily_router
from app.services import auth_service, daily_service, writing_service
from app.models.db import access_model
from app.models.db.user_model import User
from app.core.access_migration import migrate_access_schema
from app.core.daily_migration import migrate_daily_schema
from sqlalchemy.orm import Session
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

if hasattr(access_model, "AccountPlanChoice"):
    raise RuntimeError("후속 묶음이 섞였습니다. 묶음1 커밋 분리본에서 실행하세요.")
if not Path(writing_service.__file__).resolve().is_relative_to(Path.cwd().resolve()):
    raise RuntimeError("검사 대상 코드 경로가 분리본 밖입니다.")

app, engine = space.app, space.engine
clock = {"now": datetime(2026, 11, 3, 23, 59, 50)}
for module in (auth_service, daily_service, daily_router, writing_service, space.writing_router):
    module.get_kst_now = lambda: clock["now"]
with Session(engine) as db:
    for user in db.query(User):
        user.registered_at = clock["now"]
    db.commit()
migrate_access_schema(engine)
migrate_daily_schema(engine, clock["now"])
app.include_router(daily_router.router)


class ClockInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    now: str


@app.post("/fixture/trial-clock")
def set_clock(data: ClockInput):
    value = datetime.fromisoformat(data.now)
    if value.tzinfo or not clock["now"] <= value <= datetime(2026, 11, 11):
        raise HTTPException(422, "격리 검사 시각은 검사 기간 안에서 앞으로만 이동합니다.")
    clock["now"] = value
    return {"server_now": value.isoformat()}


@app.get("/fixture/trial-evidence")
def evidence():
    with Session(engine) as db:
        periods = db.query(access_model.AccountAccess).all()
        return {"source": "bundle1-only", "database": str(space.fixture_path),
                "server_now": clock["now"].isoformat(), "external_ai_calls": space.calls["external"],
                "accounts": len(periods), "trial_expiries": sorted({r.trial_expires_at.isoformat() for r in periods}),
                **space.status()}
