"""18000 격리 실제 AI 여정. 계정·집계·해시만 기록하고 원문/토큰은 출력하지 않는다."""
import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone, timedelta
import httpx
from tests.deployment.verify_http import png, PASSWORD

report = Path('.local-check/docker-validation/real-http-report.json')
client = httpx.Client(base_url='http://127.0.0.1:18000',timeout=300)
name = 'real-'+uuid4().hex[:8]
checks = []
scheduled_hour = datetime.now(timezone(timedelta(hours=9))).hour
def req(method,path,status=200,**kwargs):
    r=client.request(method,path,**kwargs)
    assert r.status_code==status, f'{method} {path}: {r.status_code}'
    return r.json()
def login():
    result=req('POST','/login',json={'username':name,'password':PASSWORD})
    client.headers['Authorization']='Bearer '+result['access_token']
def checkpoint(item):
    checks.append(item)
    report.write_text(json.dumps({'user':name,'checks':checks,'scheduled_hour':scheduled_hour},ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: '+item,flush=True)
def stream(writing,request_id):
    events=[]; start=time.monotonic()
    with client.stream('POST',f'/writing/{writing}/response_stream',json={'request_id':request_id}) as response:
        assert response.status_code==200
        for line in response.iter_lines():
            if line.startswith('event: '):events.append((line[7:],round(time.monotonic()-start,3)))
    assert not any(e[0]=='error' for e in events),events
    assert events[-1][0]=='saved' and any(e[0]=='bubble' for e in events),events
    return events

req('POST','/register',json={'username':name,'email':name+'@example.org','nickname':'실제연결검증','password':PASSWORD})
login()
assert req('GET','/validation/evidence')['ai_mode']=='real-budget-proxy'
before=req('GET','/account/access')
assert before['trial_state']=='active' and not before['onboarding_complete']
req('PUT','/daily/settings',json={'hour':scheduled_hour})
req('POST','/account/onboarding')
login()
assert req('GET','/account/access')['onboarding_complete']
assert req('GET','/daily/settings')['hour']==scheduled_hour
checkpoint('가입·체험·응원시간·재로그인 유지')
w=req('POST','/writing')['id']
req('POST',f'/writing/{w}/messages',json={'request_id':'m1','message':'합성 시험 자료입니다. 오늘 작은 정리 작업을 끝내고 공원을 산책해서 뿌듯했어요.'})
events=stream(w,'lamp1')
assert req('GET',f'/writing/{w}')['quota']['base_remaining']==0
checkpoint('실제 AI SSE 말풍선·저장 완료·기본1회 차감 '+str(events))
d=req('POST',f'/writing/{w}/generate/diary',json={'request_id':'diary1'})['result']['diary_id']
draft=req('GET',f'/writing/diaries/{d}')
assert draft['title'] and draft['body']
edited=req('PATCH',f'/writing/diaries/{d}',json={'version':draft['version'],'title':'실제 연결 검증 일기','body':draft['body']+'\n직접 수정한 검증 문장입니다.'})
p=req('POST',f'/writing/diaries/{d}/photos',params={'version':edited['version'],'request_id':'photo'},content=png(),headers={'Content-Type':'image/png'})
req('POST',f'/writing/diaries/{d}/save',json={'version':p['version']})
saved=req('GET',f'/writing/diaries/{d}')
assert saved['body'].endswith('직접 수정한 검증 문장입니다.') and saved['state']=='saved'
assert req('GET','/library-data/shelf')['total']==1
checkpoint('실제 AI 일기·수정·사진·저장·재조회')
for i in (1,2):
    req('POST',f'/writing/{w}/messages',json={'request_id':'extra-m'+str(i),'message':'합성 시험의 추가 이야기입니다. 산책 후 차를 마시며 편하게 쉬었어요.'})
    stream(w,'extra'+str(i))
    assert req('GET',f'/writing/{w}')['quota']['extra_remaining']==2-i
    assert req('GET',f'/writing/diaries/{d}')==saved
req('POST',f'/writing/{w}/messages',status=409,json={'request_id':'over','message':'소진 뒤 입력 차단 검증'})
checkpoint('실제 추가2회 차감·일기 불변·소진 후 입력 차단')
for plan in ('dialogue_weekly','super'):
    req('POST','/account/plan-choice',json={'request_id':'plan-'+plan,'plan':plan})
    login()
    now=req('GET','/account/access')
    assert now['selected_plan']==plan
    for key in ('features','trial_expires_at','trial_started_at'):assert now[key]==before[key]
checkpoint('선택 변경·재로그인 복원·권한/체험 불변')
deadline=time.monotonic()+480
while True:
    evidence=req('GET','/validation/evidence')
    if (evidence['letters']>=1 and evidence['fts_rows']>0 and evidence['dense_rows']>0
        and any(j['state']=='done' and j['error_type'] is None for j in evidence['jobs'])):break
    assert time.monotonic()<deadline, 'Actual scheduled AI delivery timed out'
    time.sleep(3)
checkpoint('실제 예약 Beat→Worker→AI요약/편지→DB/FTS/Chroma')
# 이 계정의 시험 일기는 폐기 대상으로 명시된 합성 자료다.
req('DELETE',f'/writing/diaries/{d}')
new=req('POST','/writing')['id']
quota=req('GET',f'/writing/{new}')['quota']
assert quota['base_remaining']==1 and quota['extra_remaining']==0
checkpoint('시험 일기 폐기 후 기본1회 복구·추가 소진 유지')
req('POST',f'/writing/{new}/messages',json={'request_id':'rewrite-m','message':'새로 쓰는 합성 시험 기록입니다. 오늘 정리를 마치고 산책한 기분을 다시 적어요.'})
stream(new,'rewrite-lamp')
newd=req('POST',f'/writing/{new}/generate/diary',json={'request_id':'rewrite-diary'})['result']['diary_id']
draft=req('GET',f'/writing/diaries/{newd}')
req('POST',f'/writing/diaries/{newd}/save',json={'version':draft['version']})
checkpoint('복구한 기본1회로 실제 AI 재작성·재저장')
req('POST','/validation/expire')
after=req('GET','/account/access')
assert after['trial_state']=='expired' and after['features']==[]
assert req('GET',f'/writing/diaries/{newd}')['state']=='saved'
assert req('GET','/daily/notices')['count']>=1
checkpoint('검증계정 만료 후 무료권한·기존 일기/편지 유지')
result={'user':name,'checks':checks,'scheduled_hour':scheduled_hour,'diary_id':newd,'writing_id':new,'evidence':evidence,'natural_week_observation':'pending'}
report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
client.close()
