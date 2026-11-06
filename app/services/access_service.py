"""기능별 이용 권한을 반환한다. 시각은 기존 DB와 같은 naive KST다."""
from datetime import datetime, timedelta
from app.models.db.access_model import AccountAccess, AccountPlanChoice
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
    end = datetime.combine(start.date() + timedelta(days=5), datetime.min.time()) if start else None
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
    features = PLANS["super"] if trial else ()
    return {"plan": "free", "features": list(features), "trial_state": "active" if trial else "expired" if end else "registration_unknown",
            "trial_days": (end.date()-start.date()).days if start and end else 5, "cycle_days": cycle_days(db, uid),
            "trial_started_at": start.isoformat() if start else None,
            "trial_expires_at": end.isoformat() if end else None}


def permits(db, uid, feature, now):
    return feature in access(db, uid, now)["features"]


def cycle_days(db, uid):
    """기존 저장된 7일 체험은 유지한다. 새 계정은 5일 정책이다."""
    row = db.get(AccountAccess, uid)
    if row and row.trial_started_at and row.trial_expires_at:
        days = (row.trial_expires_at.date() - row.trial_started_at.date()).days
        if days == 7:
            return 7
    return 5


def selected_plan(db, uid):
    row = db.query(AccountPlanChoice).filter_by(user_id=uid).order_by(AccountPlanChoice.id.desc()).first()
    return {"selected_plan":row.plan if row else None,
            "selected_at":row.chosen_at.isoformat() if row else None}


def choose_plan(db, uid, request_id, plan, now):
    """선택 의향만 저장한다. 체험·기능 권한·결제 상태는 변경하지 않는다."""
    if plan not in PLANS:
        raise ValueError("Unknown plan")
    row = db.query(AccountPlanChoice).filter_by(user_id=uid,request_id=request_id).first()
    if row:
        if row.plan != plan:
            raise ValueError("Request ID conflict")
    else:
        row = AccountPlanChoice(user_id=uid,request_id=request_id,plan=plan,chosen_at=now)
        db.add(row)
        db.flush()
    return {"selected_plan":row.plan,"selected_at":row.chosen_at.isoformat(),"grants_access":False}
