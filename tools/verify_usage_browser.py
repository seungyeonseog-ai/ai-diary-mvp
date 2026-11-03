"""묶음2 실행 서버의 HTTP 통합 검사. 격리 fixture 확인 후 합성 계정만 사용."""
import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4


def verify(port):
    base=f'http://127.0.0.1:{port}'
    token=None
    checks=[]
    def call(method,path,data=None,status=200,stream=False):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        request=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
        try:response=urllib.request.urlopen(request,timeout=20)
        except urllib.error.HTTPError as error:
            assert error.code==status,(path,error.code,status)
            return None
        with response:
            assert response.status==status,(path,response.status,status)
            text=response.read().decode()
            return text if stream else json.loads(text)
    def post(path,data=None,**kwargs):return call('POST',path,{} if data is None else data,**kwargs)
    def get(path):return call('GET',path)
    def message(writing):return post(f'/writing/{writing}/messages',{'request_id':str(uuid4()),'message':'합성 사용량 HTTP 검증 이야기'})
    def lamp(writing,key):return post(f'/writing/{writing}/response_stream',{'request_id':key},stream=True)
    def quota(writing):return get('/writing/'+writing)['quota']
    assert get('/fixture/usage-evidence')['source']=='bundle2-only'
    post('/writing',status=401)
    token=post('/login',{'username':'ui-test-2','password':'UiTest!2026'})['access_token']
    writing=post('/writing')['id'];message(writing)
    post('/fixture/fault/stream')
    assert 'event: error' in lamp(writing,'base-retry')
    q=quota(writing);assert (q['base_used'],q['base_reserved'],q['base_remaining'])==(0,0,1)
    assert 'event: saved' in lamp(writing,'base-retry')
    calls=get('/fixture/usage-evidence')['calls']['lamp']
    assert 'event: saved' in lamp(writing,'base-retry')
    assert get('/fixture/usage-evidence')['calls']['lamp']==calls
    assert quota(writing)['base_used']==1
    checks.append('기본실패미차감/동일요청재시도1회/성공재전송AI0')

    message(writing);post('/fixture/fault/complete')
    assert 'event: error' in lamp(writing,'save-retry')
    q=quota(writing);assert (q['extra_used'],q['extra_reserved'],q['extra_remaining'])==(0,0,2)
    calls=get('/fixture/usage-evidence')['calls']['lamp']
    assert 'event: saved' in lamp(writing,'save-retry')
    assert get('/fixture/usage-evidence')['calls']['lamp']==calls
    assert quota(writing)['extra_used']==1
    checks.append('생성후저장실패미차감/캐시결과재사용·AI재호출없음')

    message(writing);post('/fixture/gate/pause')
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(lamp,writing,'held')
        try:
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                q=quota(writing)
                if q['extra_reserved']==1:break
                time.sleep(.05)
            assert (q['extra_used'],q['extra_reserved'],q['extra_remaining'])==(1,1,0)
            post(f'/writing/{writing}/response_stream',{'request_id':'held'},status=409)
            post(f'/writing/{writing}/response_stream',{'request_id':'duplicate'},status=409)
        finally:post('/fixture/gate/resume')
        assert 'event: saved' in pending.result(timeout=10)
    q=quota(writing);assert (q['extra_used'],q['extra_reserved'],q['extra_remaining'])==(2,0,0)
    message(writing);calls=get('/fixture/usage-evidence')['calls']['lamp']
    post(f'/writing/{writing}/response_stream',{'request_id':'exhausted'},status=409)
    assert get('/fixture/usage-evidence')['calls']['lamp']==calls
    checks.append('처리중예약/동시·중복409/완료한번차감/추가한도AI전차단')

    old_token=token
    token=post('/login',{'username':'ui-test-1','password':'UiTest!2026'})['access_token']
    call('GET','/writing/'+writing,status=404)
    other=post('/writing')['id'];assert quota(other)['extra_used']==0
    token=old_token
    checks.append('계정별사용량격리/타계정404')

    call('DELETE','/writing/'+writing)
    new=post('/writing')['id'];q=quota(new)
    assert (q['base_remaining'],q['extra_used'],q['extra_remaining'])==(1,2,0)
    message(new);post('/fixture/gate/pause')
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(lamp,new,'midnight')
        try:
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                q=quota(new)
                if q['base_reserved']==1:break
                time.sleep(.05)
            assert (q['base_used'],q['base_reserved'])==(0,1)
            post('/fixture/trial-clock',{'now':'2026-11-04T00:00:00'})
        finally:post('/fixture/gate/resume')
        assert 'event: error' in pending.result(timeout=10)
    today=post('/writing')['id'];q=quota(today)
    assert (q['base_remaining'],q['base_reserved'],q['extra_used'],q['extra_reserved'],q['extra_remaining'])==(1,0,0,0,2)
    assert get('/fixture/usage-evidence')['external_ai_calls']==0
    checks.append('하루추가공유/자정늦은완료미차감/새날짜기본·추가보존')
    result={'port':port,'real_http':True,'checks':checks,'external_ai_calls':0}
    print(json.dumps(result,ensure_ascii=False))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,choices=(8018,8022),default=8018)
    verify(parser.parse_args().port)
