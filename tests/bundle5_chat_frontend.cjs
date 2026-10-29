const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('static/js/components/chatting/section.js','utf8');
async function run(text, fail=false) {
 const box={children:[],appendChild(x){this.children.push(x)}},ctx=vm.createContext({window:{},TextDecoder,document:{createElement:()=>({style:{}})},console});
 vm.runInContext(source,ctx);
 const bytes=new TextEncoder().encode(text);let n=0;
 await ctx.handleChatResponse({body:{getReader:()=>({read:async()=>{if(n<bytes.length)return {done:false,value:bytes.slice(n,++n)};if(fail)throw Error('network');return {done:true}}})}},box);
 return {text:box.children[0].textContent,status:box.children[1].textContent,ctx};
}
(async()=>{
 let r=await run('event: chunk\ndata: {"text":"합성\\n답변"}\n\nevent: saved\ndata: {}\n\n');assert.equal(r.text,'합성\n답변');assert.equal(r.status,'저장 완료');assert.equal(vm.runInContext('messages.length',r.ctx),1);
 for(const code of ['generation_failed','save_failed']){r=await run(`event: chunk\ndata: {"text":"일부 답변"}\n\nevent: error\ndata: {"code":"${code}","message":"${code}"}\n\n`);assert.equal(r.status,code);assert.equal(vm.runInContext('messages.length',r.ctx),0)}
 for(const fail of [false,true]){r=await run('event: chunk\ndata: {"text":"일부"}\n\n',fail);assert.match(r.status,/확인하지 못했습니다/);assert.equal(vm.runInContext('messages.length',r.ctx),0)}
 r=await run('event: chunk\ndata: {"text":"<img src=x onerror=alert(1)>"}\n\nevent: saved\ndata: {}\n\n');assert.equal(r.text,'<img src=x onerror=alert(1)>');
 console.log('PASS chat SSE: 6 scenarios with single-byte UTF-8 boundaries');
})().catch(e=>{console.error(e);process.exitCode=1});
