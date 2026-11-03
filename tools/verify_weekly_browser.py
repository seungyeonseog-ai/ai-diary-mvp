"""묶음8 격리 HTTP: 7일/3날짜 생성, 늦은 사용 만료 차단, 기존 결과."""
import argparse,json,urllib.request,urllib.error
from uuid import uuid4
def verify(expire=False):
 base='http://127.0.0.1:8018';token=None
 def call(method,path,data=None,status=200):
  headers={'Content-Type':'application/json'}
  if token:headers['Authorization']='Bearer '+token
  req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
  try:r=urllib.request.urlopen(req,timeout=30)
  except urllib.error.HTTPError as e:assert e.code==status,(path,e.code,status);return
  with r:assert r.status==status;return json.loads(r.read())
 def post(path,data=None,**kw):return call('POST',path,data or {},**kw)
 def get(path):return call('GET',path)
 def login(account):
  nonlocal token
  token=post('/login',{'username':f'ui-test-{account}','password':'UiTest!2026'})['access_token']
 def at(value):post('/fixture/clock',{'now':value})
 def message():
  w=post('/writing')['id'];post(f'/writing/{w}/messages',{'request_id':uuid4().hex,'message':'주간 조건과 기존 결과 열람을 확인하는 합성 이야기입니다.'})
 initial=get('/fixture/integration-status');assert initial['external_ai_calls']==0
 call('GET','/study/weekly/latest',status=401)
 if not expire:
  for day,account in ((3,1),(4,2),(5,1),(6,2),(9,1)):
   at(f'2026-11-{day:02}T12:00:00');login(account);post('/account/onboarding');message()
   at(f'2026-11-{day:02}T23:51:00');result=post('/fixture/tick')
   if day<9:assert result['weekly_analyses']==0
  assert result['weekly_analyses']==1 and result['daily_analyses']==5
  before=len(result['generated']);assert len(post('/fixture/tick')['generated'])==before
  login(1);weekly=get('/study/weekly/latest');assert [d['date_str'] for d in weekly['diary_analyses']]==['2026-11-03','2026-11-05','2026-11-09']
  key=weekly['weekly_analysis']['id'];login(2);call('GET',f'/study/seven-day-report/{key}',status=404);call('GET','/study/weekly/latest',status=404)
 else:
  login(1);before=get('/study/weekly/latest');key=before['weekly_analysis']['id']
  at('2026-11-10T12:00:00');login(2);message();at('2026-11-10T23:51:00')
  result=post('/fixture/tick');assert result['weekly_analyses']==1 and result['daily_analyses']==6
  fresh=result['generated'][len(initial['generated']):];assert not any(r['kind'] in ('emotion','keyword','comprehensive') for r in fresh)
  assert any(r['kind']=='daily' for r in fresh)
  call('GET','/study/weekly/latest',status=404);call('GET',f'/study/seven-day-report/{key}',status=404)
  assert get('/account/access')['features']==[]
  post('/account/plan-choice',{'request_id':uuid4().hex,'plan':'super'});assert get('/account/access')['features']==[]
  login(1);assert get('/study/weekly/latest')==before
 print(json.dumps({'real_http':True,'expired':expire,'weekly_results':result['weekly_analyses'],'daily_results':result['daily_analyses'],'checks':['7일·3날짜','조기도착없음','원본3날짜일치','중복생성없음','타계정404'] if not expire else ['늦은첫사용만료차단','무료하루분석유지','의향선택권한미부여','기존주간결과불변·열람'],'external_ai_calls':0},ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--expire',action='store_true');verify(p.parse_args().expire)
