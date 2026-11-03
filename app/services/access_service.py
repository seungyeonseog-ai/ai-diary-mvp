"""기능별 이용 권한을 반환한다. 시각은 기존 DB와 같은 naive KST다."""
from datetime import datetime, timedelta
from uuid import uuid4
from app.models.db.access_model import AccountAccess, AccessChange
from app.models.db.user_model import User

PLANS = {
    "free": (),
    "dialogue_encouragement": ("dialogue", "encouragement"),
    "dialogue_weekly": ("dialogue", "weekly"),
    "encouragement_weekly": ("encouragement", "weekly"),
    "super": ("dialogue", "encouragement", "weekly"),
}


def trial_period(user):
    start = user.trial_started_at or user.registered_at
    end = datetime.combine(start.date() + timedelta(days=7), datetime.min.time()) if start else None
    return start, end


def ensure_account(db, user):
    row = db.get(AccountAccess, user.id)
    if row is None:
        start, end = trial_period(user)
        row = AccountAccess(user_id=user.id, trial_started_at=start, trial_expires_at=end, plan="free")
        db.add(row)
        db.flush()
    return row


def access(db, uid, now):
    user = db.get(User, uid)
    if user is None:
        raise ValueError("Unknown account")
    row = db.get(AccountAccess, uid)
    start, end = (row.trial_started_at, row.trial_expires_at) if row else trial_period(user)
    trial = start is not None and start <= now < end
    paid = bool(row and row.pass_started_at and row.pass_expires_at and
                row.pass_started_at <= now < row.pass_expires_at and row.plan in PLANS)
    plan = row.plan if paid else "free"
    features = PLANS["super"] if trial else PLANS[plan]
    return {"plan": plan, "features": list(features), "trial_state": "active" if trial else "expired" if end else "registration_unknown",
            "trial_started_at": start.isoformat() if start else None,
            "trial_expires_at": end.isoformat() if end else None,
            "pass_expires_at": row.pass_expires_at.isoformat() if row and row.pass_expires_at else None,
            "cancelled_at": row.cancelled_at.isoformat() if row and row.cancelled_at else None}


def permits(db, uid, feature, now):
    return feature in access(db, uid, now)["features"]


def update_pass(db, uid, request_id, plan, now, expires_at=None, cancel=False):
    """검증된 서버 측 권한 부여용. HTTP 결제/무료 권한 발급 API가 아니다.

    호출자는 계정 잠금 트랜잭션을 소유하고 종료일의 신뢰성을 보장해야 한다.
    기간 중 변경은 기존 종료일을 유지한다. 해지는 권한을 즉시 회수하지 않는다.
    """
    if plan not in PLANS:
        raise ValueError("Unknown plan")
    old = db.query(AccessChange).filter_by(user_id=uid, request_id=request_id).first()
    action = "cancel" if cancel else "change"
    if old:
        if old.action != action or (not cancel and old.new_plan != plan):
            raise ValueError("Request ID conflict")
        return old
    row = ensure_account(db, db.get(User, uid))
    active = row.pass_expires_at is not None and now < row.pass_expires_at
    if cancel:
        if not active or row.plan == "free":
            raise ValueError("No active pass")
        row.cancelled_at = row.cancelled_at or now
        target = row.plan
    else:
        if plan == "free":
            raise ValueError("Active passes must be cancelled until period end")
        end = row.pass_expires_at if active else expires_at
        if end is None or end <= now:
            raise ValueError("A trusted future expiry is required")
        target = plan
        row.pass_started_at = row.pass_started_at if active else now
        row.pass_expires_at, row.cancelled_at = end, None
    change = AccessChange(id=str(uuid4()), user_id=uid, request_id=request_id,
                          action=action, old_plan=row.plan, new_plan=target,
                          effective_at=now, expires_at=row.pass_expires_at)
    row.plan = target
    db.add(change)
    return change
