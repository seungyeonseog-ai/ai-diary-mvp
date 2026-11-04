"""브라우저 조작 후 지정 시험 계정의 서버 상태만 읽어 집계/해시를 기록."""
import argparse
import hashlib
import json
from pathlib import Path
import httpx

parser=argparse.ArgumentParser()
parser.add_argument('--user',required=True)
parser.add_argument('--label',required=True)
args=parser.parse_args()
if not (args.user.startswith('screenflow') or args.user.startswith('weeklyscreen')):
    raise ValueError('Only named synthetic browser accounts are permitted')
with httpx.Client(base_url='http://127.0.0.1:18000',timeout=180) as client:
    response=client.post('/login',json={'username':args.user,'password':'SyntheticDocker!2026'})
    response.raise_for_status()
    client.headers['Authorization']='Bearer '+response.json()['access_token']
    def get(path):
        response=client.get(path);response.raise_for_status();return response.json()
    access=get('/account/access')
    diaries=get('/writing/diaries')
    result={'user':args.user,'label':args.label,
        'access':{key:access.get(key) for key in ('trial_started_at','trial_expires_at','trial_state','features','selected_plan','onboarding_complete')},
        'settings':get('/daily/settings'),'diary_total':diaries['total'],
        'diaries':[{'id':d['id'],'title':d['title'],'state':d['state'],'version':d['version'],
                    'body_sha256':hashlib.sha256(d['body'].encode()).hexdigest()} for d in diaries['items']],
        'aggregate':get('/validation/evidence')}
path=Path('.local-check/docker-validation/ui-server-evidence.json')
records=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
records.append(result)
path.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
