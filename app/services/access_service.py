"""기능별 이용 권한을 반환한다. 시각은 기존 DB와 같은 naive KST다."""
from datetime import datetime, timedelta
from app.models.db.access_model import AccountAccess
from app.models.db.user_model import User

TRIAL_FEATURES = ("dialogue", "encouragement", "weekly")


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
    features = TRIAL_FEATURES if trial else ()
    return {"plan": "free", "features": list(features), "trial_state": "active" if trial else "expired" if end else "registration_unknown",
            "trial_started_at": start.isoformat() if start else None,
            "trial_expires_at": end.isoformat() if end else None}


def permits(db, uid, feature, now):
    return feature in access(db, uid, now)["features"]
