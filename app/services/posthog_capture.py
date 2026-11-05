"""Explicit, opt-in product analytics for committed writing events."""
import hashlib
import hmac
import json
import logging
import os
from urllib.request import Request, urlopen

from app.utils.time_utils import KST

logger = logging.getLogger(__name__)
HOSTS = {"https://us.i.posthog.com", "https://eu.i.posthog.com"}


def capture_first_save(user_id, writing_id, diary_id, saved_at, has_photo):
    token = os.getenv("POSTHOG_PROJECT_TOKEN", "").strip()
    host = os.getenv("POSTHOG_HOST", "").strip().rstrip("/")
    key = os.getenv("POSTHOG_ID_KEY", "").strip()
    environment = os.getenv("POSTHOG_ENVIRONMENT", "").strip()
    if not token or host not in HOSTS or not key or environment != "validation":
        return

    def pseudonym(kind, value):
        return hmac.new(key.encode(), f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()

    timestamp = saved_at.replace(tzinfo=KST).isoformat()
    payload = {
        "api_key": token,
        "event": "diary_first_saved",
        "timestamp": timestamp,
        "properties": {
            "distinct_id": pseudonym("account", user_id),
            "event_id": pseudonym("first-save", f"{user_id}:{diary_id}"),
            "writing_id": pseudonym("writing", f"{user_id}:{writing_id}"),
            "diary_id": pseudonym("diary", f"{user_id}:{diary_id}"),
            "schema_version": 1,
            "occurred_at": timestamp,
            "activity_date_kst": saved_at.date().isoformat(),
            "environment": environment,
            "account_kind": "test",
            "usage_context": "internal_test",
            "has_photo": has_photo,
            "$process_person_profile": False,
            "$geoip_disable": True,
        },
    }
    request = Request(
        host + "/i/v0/e/",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=3):
            pass
    except (OSError, ValueError) as exc:
        logger.warning("posthog_first_save_delivery_failed type=%s", type(exc).__name__)
