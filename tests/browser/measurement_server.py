"""계측 보완 실제 UI 검증. 별도 합성 DB, 외부 AI·PostHog 전송 없음."""
import os
os.environ['POSTHOG_PROJECT_TOKEN'] = ''
from tests.browser import integration_server as fixture
from app.api.routers import writing_router, daily_router

app = fixture.app
events = []


def capture(name, user_id, occurrence, occurred_at, **properties):
    events.append({'event': name, 'user_id': user_id, 'occurrence': str(occurrence),
                   'properties': {key: str(value) for key, value in properties.items()}})


writing_router.capture_writing_event = capture
daily_router.capture_writing_event = capture
writing_router.capture_first_save = lambda *args, **kwargs: None


@app.get('/fixture/measurement-events')
def measurement_events():
    return {'events': events, 'external_ai_calls': 0, 'external_analytics_calls': 0}
