"""새 UI 연결용 API. 기존 /chat·/study 계약은 유지한다."""
import json
import asyncio
import logging
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from sqlalchemy.orm import Session
from app.core.connection import get_db
from app.api.dependencies.auth_dependencies import get_current_user
from app.models.db.user_model import User
from app.models.db.study_model import DiaryReport
from app.models.db.writing_model import Writing, DiaryPhoto, WritingOperation
from app.services import writing_service as service
from app.utils.time_utils import get_kst_now, KST
from fastapi.responses import StreamingResponse
from app.services.writing_stream import response_events

router = APIRouter(prefix="/writing", tags=["writing"])
logger = logging.getLogger(__name__)
MAX_PHOTO_BYTES = 20 * 1024 * 1024


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestId(Input):
    request_id: StrictStr = Field(min_length=1, max_length=80)


class MessageInput(RequestId):
    message: StrictStr = Field(min_length=1, max_length=50000)

    @field_validator("message", "request_id")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("빈 입력은 사용할 수 없습니다.")
        return value


class VersionInput(Input):
    version: int = Field(ge=1, strict=True)


class EditInput(VersionInput):
    title: StrictStr = Field(min_length=1, max_length=500)
    body: StrictStr = Field(min_length=1, max_length=50000)

    @field_validator("title", "body")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("제목과 본문을 입력해 주세요.")
        return value


def execute(function, *args):
    try:
        return function(*args)
    except service.WritingError as exc:
        raise HTTPException(exc.status, exc.message) from None
    except Exception as exc:
        logger.error("writing_request_failed type=%s", type(exc).__name__)
        raise HTTPException(503, "처리를 완료하지 못했습니다. 입력을 유지하고 같은 요청으로 다시 시도해 주세요.") from None


@router.post("")
def start(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = execute(service.start_writing, db.get_bind(), user.id)
    return {"id": row.id, "date": row.source_date, "state": row.state}


@router.get("/diaries")
def diaries(month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
            offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(DiaryReport).filter_by(user_id=user.id, state="saved")
    if month:
        from datetime import datetime
        try:
            start = datetime.fromisoformat(month+"-01")
            end = start.replace(year=start.year+1, month=1) if start.month == 12 else start.replace(month=start.month+1)
        except ValueError:
            raise HTTPException(422, "올바른 연월을 선택해 주세요.") from None
        query = query.filter(DiaryReport.timestamp >= start, DiaryReport.timestamp < end)
    total = query.count()
    rows = query.order_by(DiaryReport.timestamp.desc(), DiaryReport.diary_id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [service.diary_payload(row) for row in rows]}


@router.get("/diaries/{diary_id}")
def diary(diary_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = execute(service.owned, db, DiaryReport, diary_id, user.id)
    if row.state == "discarded":
        raise HTTPException(404, "일기를 찾을 수 없습니다.")
    return {**service.diary_payload(row), "server_date":get_kst_now().date().isoformat(), "photos": [
        {"id": p.id, "url": f"/writing/diaries/{diary_id}/photos/{p.id}"}
        for p in db.query(DiaryPhoto).filter_by(user_id=user.id, diary_id=diary_id).order_by(DiaryPhoto.created_at, DiaryPhoto.id)]}


@router.post("/diaries/{diary_id}/photos")
async def upload_photo(diary_id: int, request: Request, version: int = Query(ge=1),
                       request_id: str = Query(min_length=1, max_length=80),
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # 타인에게는 크기/형식 검사 전부터 동일한 404.
    row = execute(service.owned, db, DiaryReport, diary_id, user.id)
    if row.state == "discarded":
        raise HTTPException(404, "일기를 찾을 수 없습니다.")
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_PHOTO_BYTES:
            raise HTTPException(413, "사진은 장당 20MB까지 첨부할 수 있습니다.")
        chunks.append(chunk)
    content = b"".join(chunks)
    # 확장자·클라이언트 Content-Type을 신뢰하지 않는다. 표시 가능한 래스터만 허용.
    from io import BytesIO
    from PIL import Image
    import warnings
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                media = {"JPEG":"image/jpeg", "PNG":"image/png", "WEBP":"image/webp"}.get(image.format)
                if not media:
                    raise ValueError("Unsupported image")
                image.verify()
    except Exception:
        raise HTTPException(415, "정상적인 JPG·PNG·WebP 사진을 선택해 주세요.") from None
    return execute(service.add_photo, db.get_bind(), user.id, diary_id, version, request_id, media, content)


@router.get("/diaries/{diary_id}/photos/{photo_id}")
def photo(diary_id: int, photo_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    diary = execute(service.owned, db, DiaryReport, diary_id, user.id)
    row = execute(service.owned, db, DiaryPhoto, photo_id, user.id)
    if diary.state == "discarded" or row.diary_id != diary_id:
        raise HTTPException(404, "사진을 찾을 수 없습니다.")
    return Response(row.content, media_type=row.media_type,
                    headers={"Cache-Control":"private, no-store", "X-Content-Type-Options":"nosniff"})


@router.delete("/diaries/{diary_id}/photos/{photo_id}")
def remove_photo(diary_id: int, photo_id: str, data: VersionInput,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return execute(service.delete_photo, db.get_bind(), user.id, diary_id, photo_id, data.version)


@router.patch("/diaries/{diary_id}")
def edit(diary_id: int, data: EditInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return execute(service.edit_diary, db.get_bind(), user.id, diary_id, data.version, data.title, data.body)


@router.post("/diaries/{diary_id}/save")
def save(diary_id: int, data: VersionInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return execute(service.save_diary, db.get_bind(), user.id, diary_id, data.version)


@router.delete("/diaries/{diary_id}")
def discard_diary(diary_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return execute(service.discard_diary, db.get_bind(), user.id, diary_id)


@router.get("/{writing_id}")
def current(writing_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = execute(service.owned, db, Writing, writing_id, user.id)
    messages = service.writing_messages(db, row) if row.state != "discarded" else []
    diary = db.get(DiaryReport, row.diary_id) if row.diary_id and row.state != "discarded" else None
    now = get_kst_now()
    operations = db.query(WritingOperation).filter_by(user_id=user.id, writing_id=row.id).order_by(
        WritingOperation.created_at, WritingOperation.id).all() if row.state != "discarded" else []
    return {"id": row.id, "date": row.source_date, "state": row.state, "server_now":now.replace(tzinfo=KST).isoformat(),
            "messages": [{"id": m.id, "role": m.role, "message": m.message} for m in messages],
            "diary": service.diary_payload(diary) if diary else None,
            "operations": [{"id": op.id, "request_id":op.client_id, "kind":op.kind, "state":op.state,
                            "source_ids":op.source_ids,
                            "retry_after":op.lease_until.isoformat() if op.lease_until else None,
                            "has_generated_result":op.result is not None} for op in operations],
            "quota": service.quota(db, user.id, row, now)}


@router.post("/{writing_id}/messages")
def message(writing_id: str, data: MessageInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = execute(service.add_message, db.get_bind(), user.id, writing_id, data.request_id, data.message)
    return {"id": row.id, "role": row.role, "message": row.message}


async def generate(kind, source):
    """실제 AI 어댑터. 외부 AI 승인 전 검사는 이 경계만 합성 결과로 대체한다."""
    from app.clients.gpt_api import GPTClient
    if kind == "diary":
        from app.prompt.diary_prompt import DiaryPromptService
        prompt = DiaryPromptService().generate_writing_prompt(source)
    else:
        rules = ('사용자가 한 번에 보낸 말풍선들을 함께 읽고 편한 말투로 짧게 공감하세요. '
                 '대략 2~3개 말풍선, 각각 1~2문장 정도로 자연스럽게 나누세요. '
                 '질문으로 끝내지 마세요. JSON 객체 {"bubbles":["말풍선", "말풍선"]}만 반환하세요.')
    # 사용자 원문은 명령이 아닌 자료로 분리한다.
        prompt = rules + "\n다음 JSON 문자열은 사용자 대화 자료입니다:\n" + json.dumps(source, ensure_ascii=False)
    content = ""
    client = GPTClient()
    client.async_client = client.async_client.with_options(max_retries=0)
    try:
        async for chunk in client.stream_gpt_response(prompt, max_completion_tokens=1800):
            content += chunk
    finally:
        await client.async_client.close()
        client.client.close()
    result = json.loads(content)
    if kind == "diary":
        parsed = EditInput(version=1, **result)
        return {"title": parsed.title, "body": parsed.body}
    bubbles = result.get("bubbles")
    if not isinstance(bubbles, list) or not bubbles or not all(isinstance(b, str) and b.strip() for b in bubbles):
        raise ValueError("Invalid bubbles")
    if any(b.rstrip().endswith(("?", "？")) for b in bubbles):
        raise ValueError("Question ending")
    return {"bubbles": bubbles}


@router.post("/{writing_id}/generate/{kind}")
async def create_result(writing_id: str, kind: Literal["lamp", "diary"], data: RequestId,
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    op, source = execute(service.claim_operation, db.get_bind(), user.id, writing_id, data.request_id, kind)
    if source is None:
        return {"operation_id": op.id, "state": op.state, "result": op.result}
    try:
        result = op.result
        if result is None:
            result = await asyncio.wait_for(generate(kind, source), timeout=240)
            execute(service.checkpoint_result, db.get_bind(), user.id, op.id, op.lease_token, result)
        saved = execute(service.complete_operation, db.get_bind(), user.id, op.id, op.lease_token, result)
    except Exception as exc:
        execute(service.fail_operation, db.get_bind(), user.id, op.id, op.lease_token)
        if isinstance(exc, HTTPException):
            raise
        logger.error("writing_generation_failed kind=%s type=%s", kind, type(exc).__name__)
        raise HTTPException(503, "생성하지 못했습니다. 입력은 보존됩니다. 같은 요청으로 다시 시도해 주세요.") from None
    return {"operation_id": op.id, "state": "succeeded", "result": saved}


@router.delete("/{writing_id}")
def discard(writing_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    execute(service.discard_writing, db.get_bind(), user.id, writing_id)
    return {"state": "discarded"}


@router.post("/{writing_id}/response_stream")
def stream_lamp(writing_id: str, data: RequestId, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    op, source = execute(service.claim_operation, db.get_bind(), user.id, writing_id, data.request_id, "lamp")
    return StreamingResponse(response_events(db.get_bind(), user.id, op, source),
                             media_type="text/event-stream",
                             headers={"Cache-Control":"no-store", "X-Accel-Buffering":"no"})
