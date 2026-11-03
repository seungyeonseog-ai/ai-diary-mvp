"""묶음4 실제 HTTP 검사와 실제 브라우저용 합성 일기 준비."""
import json,urllib.request,urllib.error
from uuid import uuid4
def verify():
 base='http://127.0.0.1:8018';token=None;prefix=uuid4().hex
 def call(method,path,data=None,status=200):
  headers={'Content-Type':'application/json'}
  if token:headers['Authorization']='Bearer '+token
  if data and 'request_id' in data:data={**data,'request_id':prefix+data['request_id']}
  req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
  try:r=urllib.request.urlopen(req,timeout=20)
  except urllib.error.HTTPError as e:assert e.code==status,(path,e.code,e.read().decode());return
  with r:
   assert r.status==status;text=r.read().decode();return text if 'text/event-stream' in r.headers.get('Content-Type','') else json.loads(text)
 def post(path,data=None):return call('POST',path,data or {})
 def get(path):return call('GET',path)
 assert get('/fixture/usage-evidence')['source']=='bundle2-only'
 prepared=[]
 for account in (1,2):
  token=post('/login',{'username':f'ui-test-{account}','password':'UiTest!2026'})['access_token'];w=post('/writing')['id']
  for i in range(3):
   post(f'/writing/{w}/messages',{'request_id':f'm{account}{i}','message':'폐기 후 기본만 복구되는지 확인하는 합성 이야기'})
   assert 'event: saved' in post(f'/writing/{w}/response_stream',{'request_id':f'l{account}{i}'})
  diary=post(f'/writing/{w}/generate/diary',{'request_id':f'd{account}'})['result']['diary_id']
  post(f'/writing/diaries/{diary}/save',{'version':1});prepared.append(diary)
  if account==1:continue
  count=get('/fixture/status')['user_messages']
  assert call('DELETE',f'/writing/diaries/{diary}')['can_rewrite_today']
  call('GET',f'/writing/diaries/{diary}',status=404);old=get('/writing/'+w);assert old['messages']==[] and old['diary'] is None
  new=post('/writing')['id'];q=get('/writing/'+new)['quota'];assert (q['base_remaining'],q['extra_used'],q['extra_remaining'])==(1,2,0)
  assert get('/fixture/status')['user_messages']==count
  post(f'/writing/{new}/messages',{'request_id':'new','message':'새 작성 기본 대화'})
  assert 'event: saved' in post(f'/writing/{new}/response_stream',{'request_id':'new'})
  assert get('/writing/'+new)['quota']['extra_used']==2
 token=post('/login',{'username':'ui-test-1','password':'UiTest!2026'})['access_token']
 call('DELETE',f'/writing/diaries/{prepared[1]}',status=404)
 print(json.dumps({'real_http':True,'checks':['일기폐기·숨김','기본1복구','추가2유지','원문보존','새기본사용','타계정404'],'browser_diary':prepared[0],'external_ai_calls':0},ensure_ascii=False))
if __name__=='__main__':verify()
