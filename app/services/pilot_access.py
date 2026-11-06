"""공개 파일럿 접근 제한. 초대 원문/설정은 응답이나 로그에 포함하지 않는다."""
import hashlib
import hmac
import json
import os

from fastapi import HTTPException


def restricted():
    return os.getenv("PILOT_ACCESS_MODE", "open") != "open"


def invitations():
    try:
        value = json.loads(os.getenv("PILOT_INVITATIONS", "{}"))
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def require_access(user):
    if not restricted():
        return
    ids = os.getenv("PILOT_ALLOWED_USER_IDS", "").replace(" ", "").split(",")
    invitation = invitations().get(user.username)
    invited = (isinstance(invitation, dict) and
               invitation.get("email", "").casefold() == str(user.email).casefold() and
               bool(invitation.get("digest")))
    if str(user.id) not in ids and not invited:
        raise HTTPException(403, "초대된 계정만 이용할 수 있어요.")


def require_invitation(user):
    if not restricted():
        return
    invitation = invitations().get(user.username)
    expected = invitation.get("digest", "") if isinstance(invitation, dict) else ""
    actual = hashlib.sha256((user.invite_code or "").encode()).hexdigest()
    if (not expected or not user.invite_code or not hmac.compare_digest(expected, actual)
            or invitation.get("email", "").casefold() != str(user.email).casefold()):
        raise HTTPException(403, "초대받은 아이디·이메일과 초대 코드를 확인해 주세요.")
