// 종료 결과뿐 아니라 다음 청크를 기다리는 동안의 표시와 저장 상태를 검사한다.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('static/js/components/chatting/section.js','utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness(){
 const box={children:[],appendChild(x){this.children.push(x)}}, button={disabled:false}, input={value:'합성 입력'},calls=[];
 let next,waiting;const ready=()=>new Promise(resolve=>waiting=resolve);
 let pending=ready();
 const reader={read:()=>{waiting();return new Promise(resolve=>next=resolve)},cancel:async()=>{}};
 const ctx=vm.createContext({window:{},TextDecoder,localStorage:{getItem:()=> 'synthetic-token'},document:{createElement:()=>({style:{}}),getElementById:id=>id==='input-field'?input:box,querySelector:()=>button},alert:()=>assert.fail('unexpected alert'),fetch:async(url,options)=>{calls.push({url,options});return url==='/chat/send'?{ok:true,json:async()=>({turn:1,session_id:'synthetic'})}:{ok:true,body:{getReader:()=>reader}}}});
 vm.runInContext(source,ctx);
 return {ctx,box,button,calls,wait:()=>pending,async feed(text,done=false){await pending;pending=ready();next(done?{done:true}:{done:false,value:new TextEncoder().encode(text)});await tick()}};
}
(async()=>{
 const h=harness(),run=h.ctx.sendMessage();await h.wait();
 assert.equal(h.calls[1].options.headers.Accept,'text/event-stream');
 assert.equal(h.button.disabled,true);
 await h.feed('event: chunk\ndata: {"text":"첫"}\n\n');
 assert.equal(h.box.children[2].textContent,'첫');
 assert.equal(h.box.children[3].textContent,'답변 생성 중…');
 assert.equal(vm.runInContext('messages.length',h.ctx),1);
 await h.feed('event: chunk\ndata: {"text":" 둘째"}\n\n');
 assert.equal(h.box.children[2].textContent,'첫 둘째');
 assert.equal(h.button.disabled,true);
 await h.feed('event: saved\ndata: {}\n\n');
 assert.equal(h.box.children[3].textContent,'저장 완료');
 await h.feed('',true);await run;assert.equal(h.button.disabled,false);
 assert.equal(vm.runInContext('messages.length',h.ctx),2);
 const failed=harness(),failedRun=failed.ctx.sendMessage();await failed.wait();
 await failed.feed('event: chunk\ndata: {"text":"일부"}\n\n');
 await failed.feed('event: error\ndata: {"message":"저장 실패"}\n\n');
 assert.equal(failed.box.children[3].textContent,'저장 실패');
 await failed.feed('',true);await failedRun;
 assert.equal(vm.runInContext('messages.length',failed.ctx),1);
 console.log('PASS gated stream: display before next chunk/EOF, explicit protocol, save status, button state, failed answer excluded');
})().catch(e=>{console.error(e);process.exitCode=1});
