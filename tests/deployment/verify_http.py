"""실제 격리 컨테이너 HTTP/SSE/사진/예약/계정 격리 및 재생성 후 보존 검사."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import zlib
import httpx

PASSWORD="SyntheticDocker!2026"


def png():
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\xff\x80\0'))+chunk(b'IEND',b'')


def run(base, report, after=False):
    client=httpx.Client(base_url=base,timeout=180)
    def request(method,path,status=200,**kwargs):
        response=client.request(method,path,**kwargs)
        if response.status_code!=status:raise AssertionError(f'{method} {path}: HTTP {response.status_code}, expected {status}')
        return response.json()
    def login(name):
        data=request('POST','/login',json={'username':name,'password':PASSWORD})
        client.headers['Authorization']='Bearer '+data['access_token']
    if after:
        saved=json.loads(report.read_text(encoding='utf-8'))
        login(saved['owner'])
        diary=request('GET',f"/writing/diaries/{saved['diary_id']}")
        assert diary['state']=='saved' and diary['title']=='배포 검증 기록'
        photo=client.get(saved['photo_url'])
        assert photo.status_code==200 and hashlib.sha256(photo.content).hexdigest()==saved['photo_sha256']
        now=request('GET','/validation/evidence')
        for key in ('diaries','photos','letters','fts_rows','dense_rows'):assert now[key]==saved['evidence'][key],key
        print(json.dumps({'preserved_after_recreate_or_restore':True,'aggregate_evidence':now},ensure_ascii=False),flush=True)
        client.close();return
    prefix='docker-'+uuid4().hex[:8]
    names=[prefix+'-owner',prefix+'-other',prefix+'-browser']
    for name in names:
        request('POST','/register',json={'username':name,'email':name+'@example.org','nickname':'격리검증','password':PASSWORD})
    login(names[0])
    writing=request('POST','/writing')['id']
    request('POST',f'/writing/{writing}/messages',json={'request_id':'message','message':'합성 검증: 작은 일을 마치고 산책하며 하루를 돌아보았다.'})
    bubbles=[];start=time.monotonic()
    with client.stream('POST',f'/writing/{writing}/response_stream',json={'request_id':'lamp'}) as response:
        assert response.status_code==200
        for line in response.iter_lines():
            if line=='event: bubble':bubbles.append(time.monotonic()-start)
    assert len(bubbles)==2 and bubbles[1]-bubbles[0]>1,bubbles
    print('PASS: real HTTP SSE first/subsequent bubbles separated before completion',flush=True)
    response=request('POST',f'/writing/{writing}/generate/diary',json={'request_id':'diary'})
    diary=response['result']['diary_id']
    repeat=request('POST',f'/writing/{writing}/generate/diary',json={'request_id':'diary'})
    assert repeat['result']['diary_id']==diary
    photo=request('POST',f'/writing/diaries/{diary}/photos',params={'version':1,'request_id':'photo'},content=png(),headers={'Content-Type':'image/png'})
    request('POST',f'/writing/diaries/{diary}/save',json={'version':photo['version']})
    assert request('GET','/library-data/shelf')['total']==1
    photo_url=f"/writing/diaries/{diary}/photos/{photo['id']}"
    assert client.get(photo_url).content==png()
    request('POST',f'/writing/diaries/{diary}/save',json={'version':0},status=422)
    request('PUT','/daily/settings',json={'hour':datetime.now(timezone(timedelta(hours=9))).hour})
    print('PASS: diary/photo/save/reload; waiting for real Beat -> Worker -> database/index delivery',flush=True)
    deadline=time.monotonic()+240
    while True:
        evidence=request('GET','/validation/evidence')
        if evidence['letters']==1 and evidence['fts_rows']>0 and evidence['dense_rows']>0 and any(j['state']=='done' for j in evidence['jobs']):break
        if time.monotonic()>deadline:raise AssertionError('Scheduled delivery did not complete: '+json.dumps(evidence))
        time.sleep(2)
    print('PASS: real scheduled letter + shared FTS + Chroma index',flush=True)
    login(names[1])
    for path in (f'/writing/{writing}',f'/writing/diaries/{diary}',photo_url):request('GET',path,status=404)
    assert request('GET','/library-data/shelf')['total']==0
    assert request('GET','/daily/notices')['count']==0
    client.headers.pop('Authorization')
    request('GET',f'/writing/diaries/{diary}',status=401)
    saved={'owner':names[0],'other':names[1],'browser':names[2],'diary_id':diary,'writing_id':writing,
        'photo_url':photo_url,'photo_sha256':hashlib.sha256(png()).hexdigest(),
        'sse_bubble_seconds':bubbles,'evidence':evidence}
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':'HTTP/SSE/photo/isolation/scheduled/shared-index','evidence':evidence},ensure_ascii=False),flush=True)
    client.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',default='http://127.0.0.1:18000')
    parser.add_argument('--report',type=Path,default=Path('.local-check/docker-validation/http-report.json'))
    parser.add_argument('--after',action='store_true')
    args=parser.parse_args()
    run(args.base,args.report,args.after)
