"""합성 8번 종단 여정. python -m tools.verify_journey (외부 AI 0회)."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from tests.browser.integration_server import app, evidence


def verify():
    client = TestClient(app)
    checks = []

    def request(method, path, status=200, **kwargs):
        response = client.request(method, path, **kwargs)
        assert response.status_code == status, (method, path, response.status_code)
        return response.json()

    def at(value):
        request('POST', '/fixture/clock', json={'now': value})

    def tick():
        return request('POST', '/fixture/tick')

    def message(writing, key):
        return request('POST', f'/writing/{writing}/messages', json={
            'request_id': key, 'message': '합성 검증: 작은 일을 끝내고 산책했다.'})['id']

    def lamp(writing, key):
        response = client.post(f'/writing/{writing}/response_stream', json={'request_id': key})
        assert response.status_code == 200 and 'event: saved' in response.text
        assert response.text.count('event: bubble') == 2

    for name in ('journey-owner', 'journey-other'):
        data = {'username': name, 'email': name+'@example.org', 'nickname': '합성통합', 'password': 'Journey!2026'}
        request('POST', '/register', json=data)
        request('POST', '/register', status=400, json=data)
    request('POST', '/login', status=401, json={'username': 'journey-owner', 'password': 'wrong'})
    login = request('POST', '/login', json={'username': 'journey-owner', 'password': 'Journey!2026'})
    owner_token = login['access_token']
    client.headers['Authorization'] = 'Bearer '+owner_token
    assert request('GET', '/library-data/shelf')['total'] == 0
    request('GET', '/study/weekly/latest', status=404)
    request('PUT', '/daily/settings', json={'hour': 22})
    checks.append('가입/중복/잘못된로그인/본인인증/무자료')

    first = request('POST', '/writing')['id']
    first_id = message(first, 'a-message')
    lamp(first, 'a-lamp')
    result = request('POST', f'/writing/{first}/generate/diary', json={'request_id': 'a-diary'})
    discarded = result['result']['diary_id']
    request('DELETE', f'/writing/diaries/{discarded}')
    at('2026-11-03T12:00:01')
    second = request('POST', '/writing')['id']
    assert first != second
    second_id = message(second, 'b-message')
    lamp(second, 'b-lamp')
    result = request('POST', f'/writing/{second}/generate/diary', json={'request_id': 'b-diary'})
    diary = result['result']['diary_id']
    assert request('GET', '/library-data/shelf')['total'] == 0
    edited = request('PATCH', f'/writing/diaries/{diary}', json={
        'version': 1, 'title': '통합 검증 기록', 'body': '합성 검증용으로 수정한 일기입니다.'})
    request('POST', '/fixture/fault/save_after_commit')
    request('POST', f'/writing/diaries/{diary}/save', status=503, json={'version': edited['version']})
    request('POST', f'/writing/diaries/{diary}/save', json={'version': edited['version']})
    assert request('GET', '/library-data/shelf')['total'] == 1
    assert request('GET', '/library-data/month?month=2026-11')['items'][0]['id'] == diary
    assert request('GET', f'/writing/diaries/{diary}')['state'] == 'saved'
    checks.append('폐기A→새작성B/초안숨김/수정/저장응답유실→재시도/서재달력재열람')

    at('2026-11-03T22:00:00')
    state = tick()
    assert set(state['summary_ranges'][0]['ids']) == {first_id, second_id}
    inbox = request('GET', '/daily/inbox')
    letter = inbox['letter']['id']
    assert inbox['state'] == 'ready'
    before = len(state['generated'])
    assert len(tick()['generated']) == before
    request('POST', f'/daily/letters/{letter}/view')
    assert len(request('GET', '/daily/letters?view=pending')['items']) == 1
    notices = request('GET', '/daily/notices')
    request('POST', '/daily/notices/seen', json={'through_id': notices['through_id']})
    assert request('GET', '/daily/notices')['count'] == 0
    at('2026-11-03T23:00:00')
    # 완성 일기에는 추가 입력이 금지된다. 명시적으로 폐기하고 새 작성한다.
    request('POST', f'/writing/{second}/messages', status=409,
            json={'request_id': 'blocked-c', 'message': '합성 차단 검사'})
    request('DELETE', f'/writing/diaries/{diary}')
    third = request('POST', '/writing')['id']
    additional = message(third, 'c-message')
    lamp(third, 'c-lamp')
    result = request('POST', f'/writing/{third}/generate/diary', json={'request_id': 'c-diary'})
    diary = result['result']['diary_id']
    request('POST', f'/writing/diaries/{diary}/save', json={'version': 1})
    at('2026-11-03T23:50:00')
    assert tick()['daily_analyses'] == 1
    at('2026-11-04T00:00:05')
    state = tick()
    assert len(state['summary_ranges']) == 2
    assert state['summary_ranges'][1]['ids'] == [additional]
    assert request('GET', '/daily/inbox')['letter'] is None
    assert request('GET', f'/daily/letters/{letter}')['id'] == letter
    request('POST', f'/daily/letters/{letter}/save')
    assert request('GET', '/daily/letters?view=archive')['items'][0]['id'] == letter
    checks.append('예약원본A+B/중복tick/열람미처리/배지/23:50분석/자정C만/과거편지보관')

    for day in (5, 9):
        at(f'2026-11-{day:02}T12:00:00')
        writing = request('POST', '/writing')['id']
        message(writing, f'day{day}')
        at(f'2026-11-{day:02}T23:51:00')
        state = tick()
    assert state['daily_analyses'] == 3 and state['weekly_analyses'] == 1
    weekly = request('GET', '/study/weekly/latest')
    assert len(weekly['diary_analyses']) == 3
    before = len(state['generated'])
    assert len(tick()['generated']) == before
    checks.append('첫대화기준7일/3고유날짜/주간API/완료재실행중복없음')

    other = request('POST', '/login', json={'username': 'journey-other', 'password': 'Journey!2026'})
    client.headers['Authorization'] = 'Bearer '+other['access_token']
    for path in (f'/writing/{second}', f'/writing/diaries/{diary}', f'/daily/letters/{letter}', '/study/weekly/latest'):
        request('GET', path, status=404)
    assert request('GET', '/library-data/shelf')['total'] == 0
    assert request('GET', '/daily/notices')['count'] == 0
    client.headers.pop('Authorization')
    request('GET', '/daily/inbox', status=401)
    checks.append('타계정작성/일기/편지/주간/서재/알림격리/미인증401')
    report = {'checks': checks, 'evidence': evidence(), 'scope': '실제 라우터/격리DB/합성AI/고정KST; 브라우저·실제검색·Worker전달 별도'}
    Path('.local-check/step8-journey.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': checks, 'external_ai_calls': 0}, ensure_ascii=False))
    client.close()


if __name__ == '__main__':
    verify()
