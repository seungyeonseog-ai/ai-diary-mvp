"""새 UI 연결용 API. 기존 /chat·/study 계약은 유지한다."""
import json
import asyncio
import logging
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from sqlalchemy.orm import Session
from app.core.connection import get_db
from app.api.dependencies.auth_dependencies import get_current_user
from app.models.db.user_model import User
from app.models.db.study_model import DiaryReport
from app.models.db.writing_model import Writing, DiaryPhoto, WritingOperation
from app.services import writing_service as service
from app.services.posthog_capture import capture_first_save, capture_writing_event
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


def execute(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
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
def save(diary_id: int, data: VersionInput, background_tasks: BackgroundTasks,
         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    diary, first_save = execute(service.save_diary, db.get_bind(), user.id, diary_id, data.version)
    if first_save:
        background_tasks.add_task(capture_first_save, *first_save)
    return diary


@router.delete("/diaries/{diary_id}")
def discard_diary(diary_id: int, background_tasks: BackgroundTasks,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    analytics = []
    result = execute(service.discard_diary, db.get_bind(), user.id, diary_id, analytics=analytics)
    schedule_events(background_tasks, user.id, analytics)
    return result


def schedule_events(background_tasks, user_id, analytics):
    for name, key, now, properties in analytics:
        background_tasks.add_task(capture_writing_event, name, user_id, key, now, **properties)


class WritingView(Input):
    event: Literal["diary_draft_displayed", "library_entered", "saved_diary_selected", "saved_diary_displayed",
                   "saved_diary_edit_opened",
                   "library_entered_after_save", "space_entered_after_discard",
                   "space_entered", "space_input_started", "space_left",
                   "diary_prompt_shown", "diary_prompt_resolved"]
    diary_id: int | None = Field(default=None, strict=True, gt=0)
    navigation_id: UUID | None = None
    visit_id: UUID | None = None
    writing_id: UUID | None = None
    operation_id: UUID | None = None
    outcome: Literal["generate", "continue", "dismiss", "leave"] | None = None


@router.post("/analytics/view", status_code=204)
def record_view(data: WritingView, background_tasks: BackgroundTasks,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if data.event in ("space_entered", "space_input_started", "space_left",
                      "diary_prompt_shown", "diary_prompt_resolved"):
        if data.writing_id is None or data.visit_id is None or data.diary_id is not None:
            raise HTTPException(422)
        writing = execute(service.owned, db, Writing, str(data.writing_id), user.id)
        is_prompt = data.event.startswith("diary_prompt_")
        if is_prompt != (data.operation_id is not None and data.navigation_id is not None):
            raise HTTPException(422)
        if not is_prompt and (data.operation_id is not None or data.navigation_id is not None):
            raise HTTPException(422)
        if (data.event == "diary_prompt_resolved") != (data.outcome is not None):
            raise HTTPException(422)
        if is_prompt:
            op = execute(service.owned, db, WritingOperation, str(data.operation_id), user.id)
            if op.writing_id != writing.id or op.kind != "lamp" or op.state != "succeeded":
                raise HTTPException(409)
        properties = {"outcome": data.outcome} if data.outcome else {}
        occurrence = data.navigation_id or f"{writing.id}:{data.visit_id}"
        background_tasks.add_task(capture_writing_event, data.event, user.id, occurrence, get_kst_now(),
                                  writing_id=writing.id, operation_id=data.operation_id,
                                  navigation_id=data.navigation_id, visit_id=data.visit_id, **properties)
        return
    if data.operation_id is not None or data.outcome is not None:
        raise HTTPException(422)
    if data.event in ("library_entered_after_save", "space_entered_after_discard"):
        if data.diary_id is None or data.navigation_id is not None or data.visit_id is None:
            raise HTTPException(422)
        diary = execute(service.owned, db, DiaryReport, data.diary_id, user.id)
        now = get_kst_now()
        writing = None
        if data.event == "library_entered_after_save":
            if data.writing_id is not None or diary.state != "saved":
                raise HTTPException(409)
        else:
            if diary.state != "discarded":
                raise HTTPException(409)
            if data.writing_id is not None:
                writing = execute(service.owned, db, Writing, str(data.writing_id), user.id)
                if (writing.state != "active" or writing.source_date != diary.timestamp.date().isoformat()
                        or writing.created_at < diary.updated_at):
                    raise HTTPException(409)
        background_tasks.add_task(capture_writing_event, data.event, user.id, diary.diary_id, now,
                                  diary_id=diary.diary_id, visit_id=data.visit_id,
                                  writing_id=writing.id if writing else None)
        return
    if data.writing_id is not None:
        raise HTTPException(422)
    if data.event == "library_entered":
        if data.diary_id is not None or data.visit_id is None or data.navigation_id is not None:
            raise HTTPException(422)
        background_tasks.add_task(capture_writing_event, data.event, user.id, data.visit_id,
                                  get_kst_now(), visit_id=data.visit_id)
        return
    if data.diary_id is None or (data.event in ("saved_diary_selected", "saved_diary_edit_opened") and
                                (data.navigation_id is None or data.visit_id is None)):
        raise HTTPException(422)
    diary = execute(service.owned, db, DiaryReport, data.diary_id, user.id)
    is_draft = data.event == "diary_draft_displayed"
    if diary.state != ("draft" if is_draft else "saved"):
        raise HTTPException(409)
    writing_id = db.query(Writing.id).filter_by(user_id=user.id, diary_id=diary.diary_id).scalar()
    if is_draft and (diary.source_type != "ai" or not writing_id or data.navigation_id or data.visit_id):
        raise HTTPException(409)
    key = f"{diary.diary_id}:{data.navigation_id}" if data.navigation_id else diary.diary_id
    background_tasks.add_task(capture_writing_event, data.event, user.id, key, get_kst_now(),
                              writing_id=writing_id, diary_id=diary.diary_id,
                              navigation_id=data.navigation_id, visit_id=data.visit_id)


class ReplyObservation(Input):
    event: Literal["reply_first_displayed", "reply_completion_displayed", "reply_followup", "reply_screen_left"]
    attempt_id: UUID
    operation_id: UUID
    elapsed_ms: int = Field(strict=True, ge=0, le=86_400_000)
    diary_state: Literal["none", "draft", "saved"] | None = None
    action: Literal["generate_diary", "open_diary", "story_input", "story_sent", "next_reply", "navigate"] | None = None
    stage: Literal["waiting", "streaming", "completed"] | None = None


@router.post("/{writing_id}/analytics/extra-opportunity", status_code=204)
def extra_opportunity(writing_id: str, background_tasks: BackgroundTasks,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = get_kst_now()
    writing = execute(service.owned, db, Writing, writing_id, user.id)
    execute(service.writable, writing, now)
    quota = service.quota(db, user.id, writing, now)
    unresolved = db.query(WritingOperation.id).filter_by(writing_id=writing_id, user_id=user.id).filter(
        WritingOperation.state.in_(("pending", "failed"))).first()
    if quota["base_used"] and quota["extra_remaining"] and not unresolved:
        background_tasks.add_task(capture_writing_event, "extra_reply_available", user.id,
                                  now.date().isoformat(), now, writing_id=writing_id)
        return
    raise HTTPException(409)


@router.post("/{writing_id}/analytics/reply", status_code=204)
def reply_observed(writing_id: str, data: ReplyObservation, background_tasks: BackgroundTasks,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    op = execute(service.owned, db, WritingOperation, str(data.operation_id), user.id)
    if op.kind != "lamp" or op.writing_id != writing_id:
        raise HTTPException(404)
    if data.event in ("reply_completion_displayed", "reply_followup") and op.state != "succeeded":
        raise HTTPException(409)
    properties = data.model_dump(include={"elapsed_ms", "diary_state", "action", "stage"}, exclude_none=True)
    key = f"{op.id}:{data.attempt_id}"
    background_tasks.add_task(capture_writing_event, data.event, user.id, key, get_kst_now(),
                              writing_id=writing_id, operation_id=op.id, attempt_id=data.attempt_id,
                              reply_kind=op.quota_kind, activity_date_kst=op.source_date, **properties)


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
def message(writing_id: str, data: MessageInput, background_tasks: BackgroundTasks,
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    analytics = []
    row = execute(service.add_message, db.get_bind(), user.id, writing_id, data.request_id, data.message,
                  analytics=analytics)
    schedule_events(background_tasks, user.id, analytics)
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
async def create_result(writing_id: str, kind: Literal["lamp", "diary"], data: RequestId, background_tasks: BackgroundTasks,
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    op, source = execute(service.claim_operation, db.get_bind(), user.id, writing_id, data.request_id, kind)
    if source is None:
        result = {"diary_id": op.result["diary_id"]} if kind == "diary" else op.result
        return {"operation_id": op.id, "state": op.state, "result": result}
    analytics = []
    try:
        result = op.result
        if result is None:
            result = await asyncio.wait_for(generate(kind, source), timeout=240)
            execute(service.checkpoint_result, db.get_bind(), user.id, op.id, op.lease_token, result)
        saved = execute(service.complete_operation, db.get_bind(), user.id, op.id, op.lease_token, result,
                        analytics=analytics)
    except Exception as exc:
        execute(service.fail_operation, db.get_bind(), user.id, op.id, op.lease_token)
        if isinstance(exc, HTTPException):
            raise
        logger.error("writing_generation_failed kind=%s type=%s", kind, type(exc).__name__)
        raise HTTPException(503, "생성하지 못했습니다. 입력은 보존됩니다. 같은 요청으로 다시 시도해 주세요.") from None
    schedule_events(background_tasks, user.id, analytics)
    return {"operation_id": op.id, "state": "succeeded", "result": saved}


@router.delete("/{writing_id}")
def discard(writing_id: str, background_tasks: BackgroundTasks,
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    analytics = []
    execute(service.discard_writing, db.get_bind(), user.id, writing_id, analytics=analytics)
    schedule_events(background_tasks, user.id, analytics)
    return {"state": "discarded"}


@router.post("/{writing_id}/response_stream")
def stream_lamp(writing_id: str, data: RequestId, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
                user: User = Depends(get_current_user), attempt_id: UUID | None = None):
    op, source = execute(service.claim_operation, db.get_bind(), user.id, writing_id, data.request_id, "lamp")
    analytics = []
    bind, user_id = db.get_bind(), user.id
    attempt_id = attempt_id if source is not None else None
    headers = {"Cache-Control":"no-store", "X-Accel-Buffering":"no"}
    if attempt_id is not None:
        headers["X-Writing-Operation"] = op.id
        if op.result is not None:
            headers["X-Writing-Cached-Reply"] = "1"
        schedule_events(background_tasks, user_id, [(
            "reply_requested", f"{op.id}:{attempt_id}", get_kst_now(),
            {"writing_id": writing_id, "operation_id": op.id, "attempt_id": attempt_id,
             "reply_kind": op.quota_kind},
        )])

    async def frames():
        async for frame in response_events(bind, user_id, op, source, analytics=analytics, attempt_id=attempt_id):
            schedule_events(background_tasks, user_id, analytics)
            analytics.clear()
            yield frame

    return StreamingResponse(frames(), background=background_tasks,
                             media_type="text/event-stream",
                             headers=headers)
