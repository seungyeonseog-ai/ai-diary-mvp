const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
(async()=>{
 let accountToken=null;
 const context=vm.createContext({window:{addEventListener(){}},document:{},localStorage:{getItem(){return accountToken}},sessionStorage:{},TextDecoder,Uint8Array,URL,crypto:require('node:crypto').webcrypto,setTimeout,clearTimeout});
 const module=new vm.SourceTextModule(fs.readFileSync('static/js/space/ui.js','utf8'),{context});await module.link(()=>{});await module.evaluate();const read=module.namespace.readSSE;
 const tick=()=>new Promise(resolve=>setImmediate(resolve));
 function harness(){let controller;const stream=new ReadableStream({start(c){controller=c}});return{response:new Response(stream,{headers:{'content-type':'text/event-stream'}}),feed(text){controller.enqueue(new TextEncoder().encode(text))},end(){controller.close()}};}
 const h=harness(),bubbles=[];let finished=false;const run=read(h.response,text=>bubbles.push(text)).then(()=>{finished=true});
 h.feed('event: bubble\r');await tick();assert.equal(bubbles.length,0);
 h.feed('\ndata: {"index":0,"text":"첫 완성 말풍선"}\r\n\r\n');await tick();assert.deepEqual(bubbles,['첫 완성 말풍선']);assert.equal(finished,false);
 h.feed('event: bubble\ndata: {"index":1,"text":"둘째 말풍선"}\n\n');await tick();assert.equal(bubbles.length,2);assert.equal(finished,false);
 h.feed('event: saved\ndata: {}\n\n');h.end();await run;assert.equal(finished,true);
 const missing=harness();const fail=read(missing.response,()=>{});missing.feed('event: bubble\ndata: {"index":0,"text":"일부"}\n\n');missing.end();await assert.rejects(fail,/끊겼/);
 const error=harness();const errorRun=read(error.response,()=>{});error.feed('event: error\ndata: {"message":"저장 실패"}\n\n');await assert.rejects(errorRun,/저장 실패/);
 const changed=harness();const changedRun=read(changed.response,()=>assert.fail('stale content displayed'),()=>false);changed.feed('event: bubble\ndata: {"index":0,"text":"이전 계정"}\n\n');await assert.rejects(changedRun,/계정/);
 const sequence=harness();const sequenceRun=read(sequence.response,()=>{});sequence.feed('event: bubble\ndata: {"index":2,"text":"순서 오류"}\n\n');await assert.rejects(sequenceRun,/순서/);
 let resolveFetch;context.fetch=()=>new Promise(resolve=>resolveFetch=resolve);accountToken='synthetic-a';
 const late=module.namespace.request('/writing/own');accountToken='synthetic-b';resolveFetch(new Response('{}'));
 await assert.rejects(late,/계정이 변경/);
 context.fetch=async()=>new Response('{}',{status:401});
 await assert.rejects(module.namespace.request('/account/me',{authRedirect:false}),/로그인/);
 assert.equal(accountToken,'synthetic-b'); // 공개 홈이 별도 처리할 수 있고 강제 이동하지 않는다.
 console.log('PASS new UI stream: complete bubble before next chunk/EOF, CRLF split, saved required, error, account change, order');
})().catch(error=>{console.error(error);process.exitCode=1});
