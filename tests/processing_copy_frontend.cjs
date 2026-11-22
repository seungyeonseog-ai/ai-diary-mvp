const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
(async()=>{
 const m=new vm.SourceTextModule(fs.readFileSync('static/js/space/writing_policy.js','utf8'));
 await m.link(()=>{});await m.evaluate();const copy=m.namespace.processingCopy;
 for(const [path,method,title] of [
  ['/writing/a/messages','POST','대화를 보내고 있어요'],
  ['/writing/a','GET','대화를 불러오고 있어요'],
  ['/writing/a/response_stream?attempt_id=x','POST','답변을 준비하고 있어요'],
  ['/writing/a/generate/diary','POST','일기를 만들고 있어요'],
  ['/writing/diaries/1/save','POST','일기를 저장하고 있어요'],
  ['/writing/diaries/1','PATCH','일기를 저장하고 있어요'],
  ['/writing/diaries/1','GET','일기를 불러오고 있어요'],
  ['/writing/diaries/1','DELETE','일기를 폐기하고 있어요'],
  ['/writing/diaries/1/photos?version=1','POST','사진을 로딩 중이에요'],
  ['/writing/diaries/1/photos/123abc-456def','GET','사진을 불러오고 있어요'],
  ['/writing/diaries/1/photos/123abc-456def','DELETE','사진을 삭제하고 있어요'],
 ]){const result=copy(path,method);assert.equal(result[0],title);assert.match(result[1],/이동해 주세요/);}
 assert.equal(m.namespace.replyReadingDelay('짧은 답변'),5000);
 assert.equal(m.namespace.replyReadingDelay('긴 답변'.repeat(1000)),15000);
 console.log('PASS 11 processing states; unchanged reply reading delay');
})().catch(e=>{console.error(e);process.exitCode=1});
