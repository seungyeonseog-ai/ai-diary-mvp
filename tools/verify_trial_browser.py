"""실행 중인 격리 체험 서버의 실제 HTTP 오류·권한 경계 검사. 운영8000 금지."""
import argparse
import json
import urllib.error
import urllib.request
from uuid import uuid4


def verify(port):
    base=f"http://127.0.0.1:{port}"
    token=None
    def call(method,path,data=None,status=200,stream=False):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        request=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
        try:
            response=urllib.request.urlopen(request,timeout=15)
        except urllib.error.HTTPError as error:
            assert error.code==status,(path,error.code,status)
            return None
        with response:
            assert response.status==status,(path,response.status,status)
            value=response.read().decode()
            return value if stream else json.loads(value)
    call('POST','/writing',{},status=401)
    token=call('POST','/login',{'username':'ui-test-2','password':'UiTest!2026'})['access_token']
    writing=call('POST','/writing',{})['id']
    quota=call('GET','/writing/'+writing)['quota']
    assert quota['trial_state']=='expired' and quota['base_remaining']==1 and quota['extra_remaining']==0
    call('POST',f'/writing/{writing}/messages',{'request_id':str(uuid4()),'message':'합성 HTTP 검증용 무료 기본 이야기'})
    value=call('POST',f'/writing/{writing}/response_stream',{'request_id':str(uuid4())},stream=True)
    assert 'event: saved' in value
    evidence=call('GET','/fixture/trial-evidence')
    ai_before=evidence['calls']['lamp']
    call('POST',f'/writing/{writing}/messages',{'request_id':str(uuid4()),'message':'합성 HTTP 검증용 추가 차단 이야기'})
    call('POST',f'/writing/{writing}/response_stream',{'request_id':str(uuid4())},status=409)
    quota=call('GET','/writing/'+writing)['quota']
    assert (quota['base_remaining'],quota['extra_remaining'])==(0,0)
    after=call('GET','/fixture/trial-evidence')
    assert after['calls']['lamp']==ai_before and after['external_ai_calls']==0
    token=call('POST','/login',{'username':'ui-test-1','password':'UiTest!2026'})['access_token']
    call('GET','/writing/'+writing,status=404)
    result={'port':port,'real_http':True,'expired_free_base_success':True,
            'extra_denied_before_ai':True,'unauthenticated':401,'other_account':404,'external_ai_calls':0}
    print(json.dumps(result))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,choices=(8018,8022),default=8022)
    verify(parser.parse_args().port)
