"""합성 검증 계정의 브라우저 스트림 대기/해제·만료 제어. 토큰 출력 없음."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
import httpx

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['close','open','expire'])
    parser.add_argument('--user',required=True)
    parser.add_argument('--base',default='http://127.0.0.1:18000')
    args=parser.parse_args()
    if urlsplit(args.base).netloc not in ('127.0.0.1:18000','127.0.0.1:18002'):
        raise RuntimeError('Only the named local validation ports are permitted')
    with httpx.Client(base_url=args.base,timeout=180) as client:
        response=client.post('/login',json={'username':args.user,'password':'SyntheticDocker!2026'})
        response.raise_for_status()
        client.headers['Authorization']='Bearer '+response.json()['access_token']
        before=client.get('/account/access').json() if args.action=='expire' else None
        path='/validation/expire' if args.action=='expire' else '/validation/gate/'+args.action
        response=client.post(path)
        response.raise_for_status()
        if before is not None:
            after=client.get('/account/access').json()
            fields=('trial_started_at','trial_expires_at','trial_state')
            report=Path('.local-check/docker-validation/expiry-evidence.json')
            report.write_text(json.dumps({'synthetic_user':args.user,'before':{k:before.get(k) for k in fields},
                'after':{k:after.get(k) for k in fields}},ensure_ascii=False,indent=2),encoding='utf-8')
        print(response.text)
