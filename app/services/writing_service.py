"""새 작성 API의 원본 범위·트랜잭션·중복 제출·초안 수명 관리.

AI 네트워크 작업은 DB 잠금 밖에서 실행한다. 기록은 원문이 아닌 ID로 연결한다.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.models.db.user_model import User
from app.models.db.session_log import SessionLog
from app.models.db.chat_message_model import ChatMessage
from app.models.db.study_model import DiaryReport
from app.models.db.writing_model import Writing, WritingMessage, WritingOperation, SummaryRange, DiaryPhoto
from app.utils.time_utils import get_kst_now
from app.services.access_service import access


class WritingError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


@contextmanager
def transaction(bind, user_id):
    with Session(bind, expire_on_commit=False) as db:
        try:
            if bind.dialect.name == "sqlite":
                db.execute(text("BEGIN IMMEDIATE"))
            else:
                db.execute(select(User.id).where(User.id == user_id).with_for_update()).scalar_one()
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def owned(db, model, key, user_id):
    row = db.get(model, key)
    if row is None or row.user_id != user_id:
        raise WritingError(404, "항목을 찾을 수 없습니다.")
    return row


def writable(row, now):
    if row.state != "active" or row.source_date != now.date().isoformat():
        raise WritingError(409, "오늘 진행 중인 작성에서만 가능합니다.")


def day_messages(db, user_id, source_date, cutoff=None):
    """응원·요약용: 폐기 여부와 무관한 해당 날짜의 사용자 원본 전체."""
    start = datetime.fromisoformat(source_date)
    end = min(start + timedelta(days=1), cutoff) if cutoff else start + timedelta(days=1)
    return db.query(ChatMessage).filter(
        ChatMessage.user_id == user_id, ChatMessage.role == "user",
        ChatMessage.timestamp >= start, ChatMessage.timestamp < end,
    ).order_by(ChatMessage.timestamp, ChatMessage.id).all()


def writing_messages(db, writing):
    return db.query(ChatMessage).join(WritingMessage, WritingMessage.message_id == ChatMessage.id).filter(
        WritingMessage.writing_id == writing.id, ChatMessage.user_id == writing.user_id,
    ).order_by(ChatMessage.id).all()


def format_users(rows):
    return "\n".join(f"USER{i}. {row.message}" for i, row in enumerate(rows, 1))


def start_writing(bind, user_id):
    now = get_kst_now()
    with transaction(bind, user_id) as db:
        existing = db.query(Writing).filter_by(user_id=user_id, source_date=now.date().isoformat()).filter(
            Writing.state != "discarded").first()
        if existing:
            return existing
        # 기존 자료도 당일 작성 진입에서 같은 일기로 연결한다.
        today_diary = db.query(DiaryReport).filter(DiaryReport.user_id==user_id,
            DiaryReport.state!='discarded', DiaryReport.timestamp>=datetime.combine(now.date(),datetime.min.time()),
            DiaryReport.timestamp<datetime.combine(now.date()+timedelta(days=1),datetime.min.time())).first()
        if today_diary:
            row=Writing(id=str(uuid4()),user_id=user_id,source_date=now.date().isoformat(),
                state='active',diary_id=today_diary.diary_id,created_at=now)
            db.add(row)
            return row
        row = Writing(id=str(uuid4()), user_id=user_id, source_date=now.date().isoformat(),
                      state="active", created_at=now)
        db.add(row)
        return row


def add_message(bind, user_id, writing_id, client_id, message):
    with transaction(bind, user_id) as db:
        row = owned(db, Writing, writing_id, user_id)
        writable(row, get_kst_now())
        old = db.query(WritingMessage).filter_by(writing_id=row.id, client_id=client_id).first()
        if old:
            msg = db.get(ChatMessage, old.message_id)
            if msg.message != message:
                raise WritingError(409, "같은 요청 ID의 내용이 변경되었습니다.")
            return msg
        if row.diary_id and quota(db, user_id, row, get_kst_now())["extra_remaining"] == 0:
            raise WritingError(409, "남은 추가 대화가 없어요. 오늘 일기를 보거나 폐기 후 다시 작성할 수 있어요.")
        if db.query(WritingOperation).filter_by(writing_id=row.id, kind="diary", state="failed").first():
            raise WritingError(409, "일기 생성 요청을 먼저 다시 시도해 주세요. 원래 이야기는 보관되어 있습니다.")
        if db.query(WritingOperation).filter_by(writing_id=row.id, state="pending").first():
            raise WritingError(409, "진행 중인 요청이 끝난 뒤 입력해 주세요.")
        # 기존 세션 ID 생성 규칙에 의존하지 않는 작성 전용 기술 세션.
        session_id = "writing-" + row.id
        if not db.query(SessionLog).filter_by(user_id=user_id, session_id=session_id).first():
            db.add(SessionLog(user_id=user_id, session_id=session_id, start_time=get_kst_now()))
            db.flush()
        msg = ChatMessage(user_id=user_id, session_id=session_id, role="user", message=message,
                          timestamp=get_kst_now(), turn=len(writing_messages(db, row)) + 1)
        db.add(msg)
        db.flush()
        db.add(WritingMessage(writing_id=row.id, message_id=msg.id, client_id=client_id))
        return msg


def quota(db, user_id, writing, now, excluding=None):
    day = now.date().isoformat()
    query = db.query(WritingOperation).filter_by(user_id=user_id, kind="lamp").filter(
        WritingOperation.state.in_(("pending", "succeeded")),
        (WritingOperation.writing_id == writing.id) | (WritingOperation.source_date == day))
    if excluding is not None:
        query = query.filter(WritingOperation.id != excluding)
    operations = query.all()
    reserved = [op for op in operations if op.state == "pending"]
    success = [op for op in operations if op.state == "succeeded"]
    base_used = any(op.writing_id == writing.id and op.quota_kind == "base" for op in success)
    base_reserved = any(op.writing_id == writing.id and op.quota_kind == "base" for op in reserved)
    extra_used = sum(op.source_date == day and op.quota_kind == "extra" for op in success)
    extra_reserved = sum(op.source_date == day and op.quota_kind == "extra" for op in reserved)
    rights = access(db, user_id, now)
    return {**rights, "base_remaining": 0 if base_used or base_reserved or writing.diary_id else 1,
            "base_used": int(base_used), "base_reserved": int(base_reserved),
            "extra_used": extra_used, "extra_reserved": extra_reserved,
            "extra_remaining": max(0, 2-extra_used-extra_reserved) if "dialogue" in rights["features"] else 0}


def claim_operation(bind, user_id, writing_id, client_id, kind):
    """같은 요청 재전송은 같은 원본/차감을 재사용. lease로 AI 작업 중복 실행 방지."""
    now = get_kst_now()
    with transaction(bind, user_id) as db:
        writing = owned(db, Writing, writing_id, user_id)
        old = db.query(WritingOperation).filter_by(user_id=user_id, client_id=client_id).first()
        if old:
            if old.writing_id != writing_id or old.kind != kind:
                raise WritingError(409, "다른 작업에 사용한 요청 ID입니다.")
            if old.state == "succeeded":
                return old, None
            writable(writing, now)
            if writing.diary_id and kind == "diary":
                raise WritingError(409, "이미 생성된 초안을 확인해 주세요.")
            if old.state == "pending" and old.lease_until and old.lease_until > now:
                raise WritingError(409, "같은 요청을 처리 중입니다.")
            if db.query(WritingOperation).filter(WritingOperation.writing_id == writing_id,
                    WritingOperation.state == "pending", WritingOperation.id != old.id).first():
                raise WritingError(409, "다른 요청을 처리 중입니다. 해당 요청을 먼저 확인해 주세요.")
            op = old
        else:
            writable(writing, now)
            if db.query(WritingOperation).filter_by(writing_id=writing_id, state="pending").first():
                raise WritingError(409, "진행 중인 요청이 있습니다. 같은 요청으로 재시도해 주세요.")
            rows = [m for m in writing_messages(db, writing) if m.role == "user"]
            if not rows:
                raise WritingError(409, "이야기를 먼저 입력해 주세요.")
            charge = None
            if kind == "lamp":
                previous_ids = {i for o in db.query(WritingOperation).filter_by(writing_id=writing_id, kind="lamp")
                                for i in o.source_ids}
                rows = [m for m in rows if m.id not in previous_ids]
                if not rows:
                    raise WritingError(409, "새로 입력한 이야기가 없습니다. 실패한 요청은 같은 ID로 재시도해 주세요.")
                allowance = quota(db, user_id, writing, now)
                charge = "base" if allowance["base_remaining"] else "extra" if allowance["extra_remaining"] else None
                if charge is None:
                    raise WritingError(409, "오늘 추가 대화 기회를 모두 사용했습니다.")
            else:
                if writing.diary_id:
                    raise WritingError(409, "이미 생성된 초안을 확인해 주세요.")
                success = db.query(WritingOperation).filter_by(writing_id=writing_id, kind="lamp", state="succeeded").all()
                submitted = {i for o in success for i in o.source_ids}
                if any(m.id not in submitted for m in rows):
                    raise WritingError(409, "입력한 이야기를 전등으로 먼저 보내 주세요.")
            op = WritingOperation(id=str(uuid4()), user_id=user_id, writing_id=writing_id,
                                  client_id=client_id, kind=kind, source_ids=[m.id for m in rows],
                                  source_date=now.date().isoformat(), quota_kind=charge, state="pending", created_at=now)
            db.add(op)
        if kind == "lamp":
            # 실패는 미차감. 재시도마다 현재 권한/사용량을 다시 판정한다.
            allowance = quota(db, user_id, writing, now, excluding=op.id)
            charge = "base" if allowance["base_remaining"] else "extra" if allowance["extra_remaining"] else None
            if charge is None:
                raise WritingError(409, "오늘 사용할 수 있는 대화 기회가 없어요. 이용권과 남은 횟수를 확인해 주세요.")
            op.quota_kind = charge
        # 재시도 원본도 서버에 고정된 ID만 읽는다.
        sources = db.query(ChatMessage).filter(ChatMessage.id.in_(op.source_ids),
                    ChatMessage.user_id == user_id, ChatMessage.role == "user").order_by(ChatMessage.id).all()
        if len(sources) != len(op.source_ids):
            raise WritingError(409, "원본 범위를 확인하지 못했습니다.")
        op.state, op.lease_token = "pending", str(uuid4())
        op.lease_until = now + timedelta(minutes=5)
        return op, format_users(sources)


def checkpoint_result(bind, user_id, operation_id, token, result):
    """생성 완료 결과를 먼저 보관해 후속 저장 재시도 시 AI를 다시 호출하지 않는다."""
    with transaction(bind, user_id) as db:
        op = owned(db, WritingOperation, operation_id, user_id)
        if op.state != "pending" or op.lease_token != token:
            raise WritingError(409, "요청 상태가 변경되었습니다.")
        op.result = result


def complete_operation(bind, user_id, operation_id, token, result):
    now = get_kst_now()
    with transaction(bind, user_id) as db:
        op = owned(db, WritingOperation, operation_id, user_id)
        if op.state != "pending" or op.lease_token != token:
            raise WritingError(409, "요청 상태가 변경되었습니다.")
        writing = owned(db, Writing, op.writing_id, user_id)
        # 날짜가 넘어가는 동안 완료한 요청은 원래 작성일을 보존한다.
        if writing.state != "active":
            raise WritingError(409, "종료된 작성입니다.")
        if op.kind == "lamp":
            if op.source_date != now.date().isoformat():
                raise WritingError(409, "날짜가 바뀌었어요. 오늘의 대화에서 다시 시작해 주세요.")
            allowance = quota(db, user_id, writing, now, excluding=op.id)
            if op.quota_kind == "extra" and allowance["extra_remaining"] == 0:
                raise WritingError(409, "추가 대화 권한이 종료되었어요. 생성 결과는 보관되며 횟수는 차감하지 않았어요.")
        if op.kind == "diary":
            start = datetime.fromisoformat(writing.source_date)
            duplicate = db.query(DiaryReport).filter(DiaryReport.user_id==user_id,
                DiaryReport.state!='discarded',DiaryReport.timestamp>=start,
                DiaryReport.timestamp<start+timedelta(days=1)).first()
            if duplicate:
                raise WritingError(409,'이미 이 날짜의 일기가 있어요. 서재에서 확인해 주세요.')
            # 폐기 원본을 보존하므로 같은 시각의 재작성도 고유 시각을 사용한다.
            timestamp = writing.created_at
            while db.query(DiaryReport.diary_id).filter_by(user_id=user_id, timestamp=timestamp).first():
                timestamp += timedelta(microseconds=1)
                if timestamp >= start + timedelta(days=1):
                    timestamp = start
            diary = DiaryReport(user_id=user_id, title=result["title"], content=result["body"],
                                source_type="ai", state="draft", version=1,
                                timestamp=timestamp, updated_at=now)
            db.add(diary)
            db.flush()
            writing.diary_id = diary.diary_id
            result = {"diary_id": diary.diary_id}
        else:
            sources = writing_messages(db, writing)
            turn = len(sources)
            for index, bubble in enumerate(result["bubbles"]):
                msg = ChatMessage(user_id=user_id, session_id="writing-"+writing.id, role="gpt",
                                  message=bubble, timestamp=now, turn=turn+index+1)
                db.add(msg)
                db.flush()
                db.add(WritingMessage(message_id=msg.id, writing_id=writing.id, client_id=f"{op.id}-{index}"))
        op.result, op.state, op.lease_until = result, "succeeded", None
        return result


def fail_operation(bind, user_id, operation_id, token):
    with transaction(bind, user_id) as db:
        op = owned(db, WritingOperation, operation_id, user_id)
        if op.state == "pending" and op.lease_token == token:
            op.state, op.lease_until = "failed", None


def diary_payload(row):
    return {"id": row.diary_id, "title": row.title, "body": row.content,
            "state": row.state, "version": row.version,
            "date": row.timestamp.date().isoformat()}


def edit_diary(bind, user_id, diary_id, version, title, body):
    with transaction(bind, user_id) as db:
        diary = owned(db, DiaryReport, diary_id, user_id)
        if diary.state == "discarded" or diary.version != version:
            raise WritingError(409, "일기가 변경되었습니다. 다시 열어 확인해 주세요.")
        diary.title, diary.content = title, body
        diary.version += 1
        diary.updated_at = get_kst_now()
        return diary_payload(diary)


def save_diary(bind, user_id, diary_id, version):
    with transaction(bind, user_id) as db:
        diary = owned(db, DiaryReport, diary_id, user_id)
        # 저장 응답 유실 후 동일 버전 재시도도 같은 행을 반환한다.
        if diary.state == "saved" and version in (diary.version, diary.version-1):
            return diary_payload(diary), None
        if diary.state != "draft" or diary.version != version:
            raise WritingError(409, "일기가 변경되었습니다. 다시 열어 확인해 주세요.")
        start=datetime.combine(diary.timestamp.date(),datetime.min.time())
        if db.query(DiaryReport).filter(DiaryReport.user_id==user_id,DiaryReport.diary_id!=diary_id,
                DiaryReport.state!='discarded',DiaryReport.timestamp>=start,
                DiaryReport.timestamp<start+timedelta(days=1)).first():
            raise WritingError(409,'이미 이 날짜의 일기가 있어요. 서재에서 확인해 주세요.')
        diary.state, diary.updated_at = "saved", get_kst_now()
        diary.version += 1
        writing_id = db.query(Writing.id).filter_by(user_id=user_id, diary_id=diary_id).scalar()
        first_save = None
        if writing_id and diary.source_type == "ai":
            has_photo = db.query(DiaryPhoto.id).filter_by(user_id=user_id, diary_id=diary_id).first() is not None
            first_save = (user_id, writing_id, diary_id, diary.updated_at, has_photo)
        return diary_payload(diary), first_save


def discard_writing(bind, user_id, writing_id):
    with transaction(bind, user_id) as db:
        writing = owned(db, Writing, writing_id, user_id)
        if writing.state == "discarded":
            return
        # 진행 작업 무효화: 늦게 온 응답이 새 일기로 저장되지 않는다.
        for op in db.query(WritingOperation).filter_by(writing_id=writing.id, state="pending"):
            op.state, op.lease_token, op.lease_until = "cancelled", None, None
        writing.state, writing.closed_at = "discarded", get_kst_now()
        if writing.diary_id:
            diary = owned(db, DiaryReport, writing.diary_id, user_id)
            diary.state, diary.updated_at = "discarded", get_kst_now()
            diary.version += 1
            db.query(DiaryPhoto).filter_by(diary_id=diary.diary_id, user_id=user_id).delete()


def discard_diary(bind, user_id, diary_id):
    # 과거 일기도 폐기 가능하지만 새 작성 API는 오늘 날짜만 생성한다.
    with transaction(bind, user_id) as db:
        diary = owned(db, DiaryReport, diary_id, user_id)
        result={"state":"discarded","date":diary.timestamp.date().isoformat(),
                "can_rewrite_today":diary.timestamp.date()==get_kst_now().date()}
        if diary.state == "discarded":
            return result
        writing = db.query(Writing).filter_by(user_id=user_id, diary_id=diary_id).first()
        if writing:
            for op in db.query(WritingOperation).filter_by(writing_id=writing.id, state="pending"):
                op.state, op.lease_token, op.lease_until = "cancelled", None, None
            writing.state, writing.closed_at = "discarded", get_kst_now()
        diary.state, diary.updated_at = "discarded", get_kst_now()
        diary.version += 1
        db.query(DiaryPhoto).filter_by(diary_id=diary.diary_id, user_id=user_id).delete()
        return result


def add_photo(bind, user_id, diary_id, version, client_id, media_type, content):
    import hashlib
    digest = hashlib.sha256(content).hexdigest()
    with transaction(bind, user_id) as db:
        diary = owned(db, DiaryReport, diary_id, user_id)
        if diary.state == "discarded":
            raise WritingError(404, "일기를 찾을 수 없습니다.")
        old = db.query(DiaryPhoto).filter_by(diary_id=diary_id, client_id=client_id).first()
        if old:
            if old.digest != digest:
                raise WritingError(409, "같은 요청 ID의 사진이 변경되었습니다.")
            return {"id": old.id, "version": diary.version}
        if version != diary.version:
            raise WritingError(409, "일기가 변경되었습니다. 다시 열어 확인해 주세요.")
        if db.query(DiaryPhoto).filter_by(diary_id=diary_id).count() >= 3:
            raise WritingError(409, "사진은 최대 3장까지 첨부할 수 있습니다.")
        photo = DiaryPhoto(id=str(uuid4()), user_id=user_id, diary_id=diary_id, client_id=client_id,
                           media_type=media_type, digest=digest, content=content, created_at=get_kst_now())
        db.add(photo)
        diary.version += 1
        diary.updated_at = get_kst_now()
        return {"id": photo.id, "version": diary.version}


def delete_photo(bind, user_id, diary_id, photo_id, version):
    with transaction(bind, user_id) as db:
        diary = owned(db, DiaryReport, diary_id, user_id)
        photo = owned(db, DiaryPhoto, photo_id, user_id)
        if diary.state == "discarded" or photo.diary_id != diary_id:
            raise WritingError(404, "사진을 찾을 수 없습니다.")
        if diary.version != version:
            raise WritingError(409, "일기가 변경되었습니다. 다시 열어 확인해 주세요.")
        db.delete(photo)
        diary.version += 1
        diary.updated_at = get_kst_now()
        return {"version": diary.version}


def unprocessed_day_messages(db, user_id, source_date, cutoff=None):
    used = {i for r in db.query(SummaryRange).filter_by(user_id=user_id, source_date=source_date)
            for i in r.source_ids}
    return [m for m in day_messages(db, user_id, source_date, cutoff) if m.id not in used]


def record_summary(bind, user_id, source_date, phase, source_ids, summary):
    """요약 성공 뒤 호출할 내부 기반 함수. 예약/검색/임베딩 연결은 6번에서 수행."""
    if phase not in ("encouragement", "midnight") or not source_ids or not summary.strip():
        raise WritingError(409, "요약 구간이 올바르지 않습니다.")
    with transaction(bind, user_id) as db:
        existing = db.query(SummaryRange).filter_by(user_id=user_id, source_date=source_date, phase=phase).first()
        if existing:
            if existing.source_ids != source_ids:
                raise WritingError(409, "이미 처리한 요약 구간입니다.")
            return existing
        if phase == "encouragement" and db.query(SummaryRange).filter_by(
                user_id=user_id, source_date=source_date, phase="midnight").first():
            raise WritingError(409, "이미 자정 마감한 날짜입니다.")
        candidates = unprocessed_day_messages(db, user_id, source_date)
        # AI 작업 시작 시 고정한 앞쪽 범위만 성공 처리. 도중에 추가된 대화는 남긴다.
        if [m.id for m in candidates[:len(source_ids)]] != source_ids:
            raise WritingError(409, "요약 원본이 겹치거나 다른 사용자/날짜의 대화입니다.")
        row = SummaryRange(id=str(uuid4()), user_id=user_id, source_date=source_date, phase=phase,
                           source_ids=source_ids, summary=summary, created_at=get_kst_now())
        db.add(row)
        return row
