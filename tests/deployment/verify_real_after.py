"""원문 출력 없이 실제 예약의 최종 done·동일 설정·무료 전환 후 결과 보존을 확인한다."""
import json
import time
from pathlib import Path
import httpx
from tests.deployment.verify_http import PASSWORD

path=Path('.local-check/docker-validation/real-http-report.json')
report=json.loads(path.read_text(encoding='utf-8'))
with httpx.Client(base_url='http://127.0.0.1:18000',timeout=180) as client:
    response=client.post('/login',json={'username':report['user'],'password':PASSWORD})
    response.raise_for_status()
    client.headers['Authorization']='Bearer '+response.json()['access_token']
    until=time.monotonic()+120
    while True:
        evidence=client.get('/validation/evidence').json()
        if any(j['state']=='done' and j['error_type'] is None for j in evidence['jobs']):break
        assert time.monotonic()<until,'Scheduled job did not reach done'
        time.sleep(2)
    assert evidence['fts_rows']==evidence['dense_rows'] and evidence['fts_rows']>0
    assert evidence['diaries']==1 and evidence['photos']==0 and evidence['letters']==1
    assert client.get('/account/access').json()['features']==[]
    settings=client.get('/daily/settings').json()
    assert settings['configured'] and settings['hour']==report.get('scheduled_hour',13)
    assert client.get('/writing/diaries/'+str(report['diary_id'])).json()['state']=='saved'
    letters=client.get('/daily/letters').json()['items']+client.get('/daily/letters?view=archive').json()['items']
    assert len(letters)==1
    letter=client.get('/daily/letters/'+str(letters[0]['id'])).json()
    assert letter['body'] and not letter['discarded']
    report['evidence']=evidence
    report['letter_id']=letters[0]['id']
    report['settings_verified']=True
    report['scheduled_fixture']='only this synthetic account message timestamps moved before 13:00; real Beat and system clock unchanged'
    report['checks'].append('예약 최종done·FTS/Chroma 집계 일치·재로그인 설정·무료 전환 후 편지 본문 조회')
path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'final_scheduled_evidence':evidence,'settings_verified':True,'letter_readable_after_expiry':True},ensure_ascii=False))
