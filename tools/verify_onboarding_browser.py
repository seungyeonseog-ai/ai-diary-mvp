"""격리 실행 서버: 체험 안내 완료·시간 저장·계정 격리·만료 전환."""
import argparse,json,urllib.request,urllib.error
from uuid import uuid4
def verify(expire=False):
 base='http://127.0.0.1:8018';token=None
 def call(method,path,data=None,status=200):
  headers={'Content-Type':'application/json'}
  if token:headers['Authorization']='Bearer '+token
  req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
  try:r=urllib.request.urlopen(req,timeout=20)
  except urllib.error.HTTPError as e:assert e.code==status,(path,e.code,status);return
  with r:assert r.status==status;return json.loads(r.read())
 def post(path,data=None,**kw):return call('POST',path,data or {},**kw)
 def get(path):return call('GET',path)
 assert get('/fixture/integration-status')['external_ai_calls']==0
 call('GET','/account/access',status=401);post('/account/onboarding',status=401)
 token=post('/login',{'username':'ui-test-2','password':'UiTest!2026'})['access_token']
 before=get('/account/access')
 if not expire:
  assert not before['onboarding_complete']
  call('PUT','/daily/settings',{'hour':24},status=422)
  result=call('PUT','/daily/settings',{'hour':21});assert result['configured'] and result['hour']==21
  post('/account/onboarding');post('/account/onboarding');after=get('/account/access');assert after['onboarding_complete']
  for key in ('trial_started_at','trial_expires_at','features'):assert before[key]==after[key]
  token=post('/login',{'username':'ui-test-1','password':'UiTest!2026'})['access_token']
  assert not get('/account/access')['onboarding_complete'];assert not get('/daily/settings')['configured']
 else:
  post('/fixture/clock',{'now':'2026-11-10T00:00:00'});after=get('/account/access');assert after['onboarding_complete'] and after['features']==[]
  token=post('/login',{'username':'ui-test-1','password':'UiTest!2026'})['access_token'];after=get('/account/access')
  assert after['onboarding_complete'] and after['features']==[] and get('/daily/settings')['configured']
 print(json.dumps({'real_http':True,'expired':expire,'checks':['미인증차단','시간검증·저장','완료기록멱등','기간보존','계정격리'] if not expire else ['종료시각무료','안내완료유지','시간설정유지'],'external_ai_calls':0},ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--expire',action='store_true');verify(p.parse_args().expire)
