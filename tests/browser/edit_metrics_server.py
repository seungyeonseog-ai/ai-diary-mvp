"""서재 수정 클릭 검증: 격리 합성 DB, 실제 제품 UI/API, 외부 전송 없음."""
from tests.browser.library_server import app, writing_router

events = []


def capture(name, user_id, occurrence, occurred_at, **properties):
    events.append({"event": name, "user_id": user_id,
                   "properties": {key: str(value) for key, value in properties.items()}})


writing_router.capture_writing_event = capture
writing_router.capture_first_save = lambda *args, **kwargs: None


@app.get('/fixture/analytics')
def analytics():
    return {"events": events, "external_ai_calls": 0, "external_analytics_calls": 0}
