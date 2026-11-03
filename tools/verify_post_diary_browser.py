"""실행 중인 격리 서버에서 일기 후 대화의 저장·권한을 확인한다."""
import json,urllib.request,urllib.error
from uuid import uuid4

def verify(port=8018):
 base=f'http://127.0.0.1:{port}';token=None;prefix=uuid4().hex
 def call(method,path,data=None,status=200):
  headers={'Content-Type':'application/json'}
  if token:headers['Authorization']='Bearer '+token
  if data and 'request_id' in data:data={**data,'request_id':prefix+data['request_id']}
  req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
  try:r=urllib.request.urlopen(req,timeout=20)
  except urllib.error.HTTPError as e:
   assert e.code==status,(path,e.code,status,e.read().decode());return
  with r:
   assert r.status==status
   text=r.read().decode()
   return text if 'text/event-stream' in r.headers.get('Content-Type','') else json.loads(text)
 def post(path,data=None,**kw):return call('POST',path,data or {},**kw)
 def get(path):return call('GET',path)
 assert get('/fixture/usage-evidence')['source']=='bundle2-only'
 token=post('/login',{'username':'ui-test-2','password':'UiTest!2026'})['access_token']
 w=post('/writing')['id']
 call('DELETE','/writing/'+w);w=post('/writing')['id']
 def message():return post(f'/writing/{w}/messages',{'request_id':str(uuid4()),'message':'합성 HTTP 추가 이야기'})
 def generate(kind,key):
  value=post(f'/writing/{w}/response_stream' if kind=='lamp' else f'/writing/{w}/generate/{kind}',{'request_id':key})
  if kind=='lamp':assert 'event: saved' in value
  return value
 message();generate('lamp','base');diary=generate('diary','diary')['result']['diary_id']
 before=get('/writing/diaries/'+str(diary));message();generate('lamp','draft-extra')
 assert get('/writing/diaries/'+str(diary))==before
 post(f'/writing/diaries/{diary}/save',{'version':1});before=get('/writing/diaries/'+str(diary))
 message();post('/fixture/fault/complete')
 assert 'event: error' in post(f'/writing/{w}/response_stream',{'request_id':'saved-extra'})
 assert get('/writing/'+w)['quota']['extra_used']==1
 calls=get('/fixture/usage-evidence')['calls']['lamp'];generate('lamp','saved-extra')
 assert get('/fixture/usage-evidence')['calls']['lamp']==calls
 assert get('/writing/diaries/'+str(diary))==before
 assert get('/writing/'+w)['quota']['extra_used']==2
 post(f'/writing/{w}/messages',{'request_id':'exhausted','message':'합성'},status=409)
 calls=get('/fixture/usage-evidence')['calls']['diary'];generate('diary','diary')
 assert get('/fixture/usage-evidence')['calls']['diary']==calls
 post(f'/writing/{w}/generate/diary',{'request_id':'another'},status=409)
 token=post('/login',{'username':'ui-test-1','password':'UiTest!2026'})['access_token']
 call('GET','/writing/'+w,status=404);call('GET','/writing/diaries/'+str(diary),status=404)
 print(json.dumps({'real_http':True,'checks':['초안후추가','저장후추가','기존일기불변','저장실패재시도AI재호출0','소진차단','캐시열람·중복생성차단','계정격리'],'external_ai_calls':0},ensure_ascii=False))

if __name__=='__main__':verify()
