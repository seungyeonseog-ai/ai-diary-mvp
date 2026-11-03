"""격리 HTTP: 예약 응원과 무료 기억 요약, 기존 편지 열람."""
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
 assert get('/fixture/integration-status')['external_ai_calls']==0
 if expire:post('/fixture/clock',{'now':'2026-11-10T13:00:00'})
 for account in (1,2):
  token=post('/login',{'username':f'ui-test-{account}','password':'UiTest!2026'})['access_token']
  if not expire:call('PUT','/daily/settings',{'hour':13});post('/account/onboarding')
  w=post('/writing')['id'];post(f'/writing/{w}/messages',{'request_id':uuid4().hex,'message':'기억 요약과 예약 응원을 확인하는 합성 이야기입니다.'})
 if not expire:post('/fixture/clock',{'now':'2026-11-03T13:00:00'})
 # 예약 마감 시각 이후 입력은 다음 자정 요약으로 처리한다.
 if expire:post('/fixture/clock',{'now':'2026-11-11T00:00:00'})
 before=get('/fixture/integration-status');result=post('/fixture/tick');again=post('/fixture/tick')
 assert result['letters']==again['letters']
 assert result['indexed_ranges']>=2
 if not expire:
  assert result['letters']==2 and result['indexed_ranges']==2
  mine=get('/daily/inbox');assert mine['state']=='ready';key=mine['letter']['id'];post(f'/daily/letters/{key}/save')
  token=post('/login',{'username':'ui-test-1','password':'UiTest!2026'})['access_token']
  call('GET',f'/daily/letters/{key}',status=404);assert get('/daily/inbox')['state']=='ready'
 else:
  assert result['letters']==before['letters'] and result['indexed_ranges']>before['indexed_ranges']
  generated=result['generated'][len(before['generated']):];assert not any(r['kind']=='letter' for r in generated)
  assert any(r['kind']=='summary' for r in generated)
  for account in (1,2):
   token=post('/login',{'username':f'ui-test-{account}','password':'UiTest!2026'})['access_token']
   assert get('/daily/inbox')['state']=='unavailable';items=get('/daily/letters?view=archive')['items'];assert len(items)==1
   assert get('/daily/letters/'+str(items[0]['id']))['saved']
 print(json.dumps({'real_http':True,'expired':expire,'letters':result['letters'],'indexed_ranges':result['indexed_ranges'],'checks':['예약생성','중복tick멱등','계정격리','기억요약·색인'] if not expire else ['신규응원차단·AI호출0','무료기억요약계속','기존편지열람'],'external_ai_calls':0},ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--expire',action='store_true');verify(p.parse_args().expire)
