"""격리 서버 실제 HTTP: 조합 선택은 권한·체험 기간을 바꾸지 않는다."""
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
 call('GET','/account/access',status=401);post('/account/plan-choice',{'request_id':'unauth','plan':'free'},status=401)
 token=post('/login',{'username':'ui-test-2','password':'UiTest!2026'})['access_token']
 if expire:post('/fixture/clock',{'now':'2026-11-10T00:00:00'})
 before=get('/account/access');key=uuid4().hex
 plans=['free','dialogue_encouragement','dialogue_weekly','encouragement_weekly','super']
 assert [p['id'] for p in before['plans']]==plans
 for i,plan in enumerate(plans):
  data={'request_id':key+str(i),'plan':plan}
  for _ in range(2):assert post('/account/plan-choice',data)['grants_access'] is False
  after=get('/account/access');assert after['selected_plan']==plan
  for field in ('features','plan','trial_started_at','trial_expires_at'):assert after[field]==before[field]
 post('/account/plan-choice',{'request_id':key+'4','plan':'free'},status=409)
 post('/account/plan-choice',{'request_id':key,'plan':'invalid'},status=422)
 post('/account/plan-choice',{'request_id':key,'plan':'free','user_id':1},status=422)
 if expire:assert before['features']==[] and before['trial_state']=='expired'
 token=post('/login',{'username':'ui-test-1','password':'UiTest!2026'})['access_token'];other=get('/account/access')
 if not expire:assert other['selected_plan'] is None
 else:assert other['features']==[] and other['trial_state']=='expired'
 print(json.dumps({'real_http':True,'expired':expire,'checks':['인증','5조합저장·변경','동일요청멱등','충돌409','잘못된값422','계정격리','권한·체험기간불변'],'external_ai_calls':0},ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--expire',action='store_true');verify(p.parse_args().expire)
