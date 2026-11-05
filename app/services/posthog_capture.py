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


def capture_first_save(user_id, writing_id, diary_id, saved_at, has_photo, edit_kind="unknown"):
    capture_writing_event("diary_first_saved", user_id, diary_id, saved_at,
                          writing_id=writing_id, diary_id=diary_id,
                          has_photo=has_photo, edit_kind=edit_kind)


def capture_writing_event(name, user_id, occurrence, occurred_at, *, writing_id=None,
                          diary_id=None, operation_id=None, navigation_id=None, visit_id=None, **properties):
    token = os.getenv("POSTHOG_PROJECT_TOKEN", "").strip()
    host = os.getenv("POSTHOG_HOST", "").strip().rstrip("/")
    key = os.getenv("POSTHOG_ID_KEY", "").strip()
    environment = os.getenv("POSTHOG_ENVIRONMENT", "").strip()
    if not token or host not in HOSTS or not key or environment != "validation":
        return

    def pseudonym(kind, value):
        return hmac.new(key.encode(), f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()

    timestamp = occurred_at.replace(tzinfo=KST).isoformat()
    for kind, value in (("writing", writing_id), ("diary", diary_id),
                        ("operation", operation_id), ("navigation", navigation_id), ("visit", visit_id)):
        if value is not None:
            properties[f"{kind}_id"] = pseudonym(kind, f"{user_id}:{value}")
    payload = {
        "api_key": token,
        "event": name,
        "timestamp": timestamp,
        "properties": {
            "distinct_id": pseudonym("account", user_id),
            "event_id": pseudonym("first-save" if name == "diary_first_saved" else name,
                                  f"{user_id}:{occurrence}"),
            "schema_version": 1,
            "occurred_at": timestamp,
            "activity_date_kst": occurred_at.date().isoformat(),
            "environment": environment,
            "account_kind": "test",
            "usage_context": "internal_test",
            **properties,
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
        logger.warning("posthog_delivery_failed event=%s type=%s", name, type(exc).__name__)
