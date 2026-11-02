"""3번 브라우저 검증 전용. 격리 DB, 합성 계정, 승인된 AI 최대 2회.

실제 앱 main/Beat/Worker를 띄우지 않아 테스트 자료가 검색 인덱스에 들어가지 않는다.
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
import json
import struct
import zlib
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.connection import Base, get_db
from app.api.routers import writing_router, auth_router
from app.models.db.user_model import User
from app.models.db.writing_model import Writing
from app.services.auth_service import get_password_hash
from app.services import writing_service as service
from app.utils.time_utils import get_kst_now

fixture_path = Path(".local-check") / ("writing-browser-" + str(uuid4()) + ".db")
engine = create_engine("sqlite:///" + fixture_path.as_posix(), connect_args={"check_same_thread":False})
Base.metadata.create_all(engine)
with Session(engine) as db:
    for i in (1,2):
        db.add(User(id=i,username=f"writing-fixture-{i}",email=f"fixture-{i}@example.org",
                    hashed_password=get_password_hash("synthetic-only-test"),nickname="합성 검증",
                    registered_at=get_kst_now()))
    db.commit()

app = FastAPI()
app.include_router(auth_router.router)
app.include_router(writing_router.router)

def isolated_db():
    with Session(engine) as db:
        yield db
app.dependency_overrides[get_db] = isolated_db
app.dependency_overrides[auth_router.get_db] = isolated_db

generation_calls = 0
original_generate = writing_router.generate

async def approved_generate(kind, source):
    global generation_calls
    if os.environ.get("WRITING_LIVE_AI") != "approved-two" or generation_calls >= 2:
        raise RuntimeError("Live AI call is not authorized or budget exhausted")
    if len(source) > 1500:
        raise RuntimeError("Synthetic source too large")
    generation_calls += 1
    return await original_generate(kind, source)
writing_router.generate = approved_generate


@app.get("/", response_class=HTMLResponse)
def page():
    return Path("tests/browser/writing.html").read_text(encoding="utf-8")


@app.get("/fixture/photo")
def image():
    def chunk(kind,data):
        return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data))
    png = (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))
           +chunk(b"IDAT",zlib.compress(b"\x00\xff\x80\x00"))+chunk(b"IEND",b""))
    return Response(png, media_type="image/png")


@app.get("/fixture/scope/{writing_id}")
def scope(writing_id: str):
    with Session(engine) as db:
        writing = db.get(Writing, writing_id)
        if not writing or writing.user_id != 1:
            raise HTTPException(404)
        current = [m for m in service.writing_messages(db,writing) if m.role == "user"]
        day = service.day_messages(db,1,writing.source_date)
        return {"writing_count":len(current), "day_count":len(day), "ai_calls":generation_calls,
                "new_writing_only":len(current)==1 and current[0].message=="새 작성 B 합성 이야기"}


@app.post("/fixture/evidence")
def evidence(data: dict):
    # 합성 자료를 포함해 본문/토큰/비밀번호는 기록하지 않는다.
    allowed = {key:value for key,value in data.items() if isinstance(value,(bool,int))}
    allowed["ai_calls"] = generation_calls
    Path(".local-check/writing-browser-evidence.json").write_text(
        json.dumps(allowed,ensure_ascii=False,indent=2),encoding="utf-8")
    return allowed
