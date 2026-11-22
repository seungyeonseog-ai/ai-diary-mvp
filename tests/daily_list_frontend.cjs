const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class El{
 constructor(tag='',cls='',text=''){this.tag=tag;this.className=cls;this.textContent=text;this.children=[];this.events={};this.dataset={};this.open=false;}
 append(...x){this.children.push(...x)}replaceChildren(...x){this.children=x;this.textContent=''}setAttribute(){}
 addEventListener(k,f){(this.events[k]??=[]).push(f)}showModal(){this.open=true}close(){this.open=false;for(const f of this.events.close||[])f()}
 text(){return this.textContent+this.children.map(x=>x.text()).join(' ')}
}
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 let identity='one',now=Date.now(),requests=[],observed=0;
 const events={},docEvents={},body=new El(),notice=new El('button'),ids={'daily-notifications':notice};
 const json=async(path)=>{if(path==='/daily/notices')return {items:[],count:0,through_id:0};return await new Promise((resolve,reject)=>requests.push({path,resolve,reject}));};
 const context=vm.createContext({Date:class extends Date{static now(){return now}},Promise,Map,Set,console,Event:class{},setInterval:()=>1,clearInterval(){},location:{pathname:'/space'},window:{addEventListener:(k,f)=>(events[k]??=[]).push(f),dispatchEvent(){}},document:{body,visibilityState:'visible',getElementById:k=>ids[k],querySelectorAll:()=>[],addEventListener:(k,f)=>docEvents[k]=f}});
 const api={json,node:(...x)=>new El(...x),token:()=>identity,owner:()=>identity,toast(){},dialog(){},logout(){},closeButton:()=>new El('button'),observeLetterOpportunity:()=>observed++};
 const stub=new vm.SyntheticModule(Object.keys(api),function(){for(const[k,v]of Object.entries(api))this.setExport(k,v)},{context});
 const mod=new vm.SourceTextModule(fs.readFileSync('static/js/space/daily.js','utf8'),{context});await mod.link(()=>stub);await mod.evaluate();
 const panel=body.children.find(x=>x.tag==='dialog'),list=mod.namespace.list;
 assert.equal(requests.length,1,'first-page prefetch');assert.equal(observed,0,'prefetch is not an impression');
 const first=list();assert.match(panel.text(),/불러오고/);assert.equal(requests.length,1,'early click shares prefetch');
 requests[0].resolve({items:[{id:1,date:'2026-11-22',viewed:false}]});await first;assert.match(panel.text(),/2026-11-22/);assert.equal(observed,1);
 panel.close();const cached=list();assert.match(panel.text(),/2026-11-22/,'cached content synchronous');await cached;assert.equal(requests.length,1);
 panel.close();now+=16000;const expired=list();assert.equal(requests.length,2);panel.close();requests[1].resolve({items:[{id:2,date:'2026-11-21'}]});await expired;assert.equal(observed,2,'closed panel does not record late response');
 events['daily:changed'][0]();assert.equal(requests.length,3);const changed=list();assert.doesNotMatch(panel.text(),/2026-11-21/);requests[2].resolve({items:[]});await changed;assert.match(panel.text(),/처리하지 않은 편지가 없어요/);
 events['daily:socket'][0]();assert.equal(requests.length,4);requests[3].reject(new Error('합성 통신 오류'));await tick();assert.match(panel.text(),/다시 불러오기/);
 const retry=list();assert.equal(requests.length,5);requests[4].resolve({items:[{id:3,date:'2026-11-20'}]});await retry;assert.match(panel.text(),/2026-11-20/);
 panel.close();events.storage[0]({key:'space:letters-revision'});assert.equal(requests.length,6);
 const superseded=list();events['daily:changed'][0]();assert.equal(requests.length,7);
 requests[5].resolve({items:[{id:4,date:'2026-11-19'}]});await tick();assert.doesNotMatch(panel.text(),/2026-11-19/,'invalidated response cannot restore old items');
 requests[6].resolve({items:[]});await superseded;await tick();assert.match(panel.text(),/처리하지 않은 편지가 없어요/);
 panel.close();now+=24*3600000;const nextDay=list();assert.equal(requests.length,8);
 identity='two';events['space:identity-cleared'][0]();requests[7].resolve({items:[{id:4,date:'2026-11-19'}]});await nextDay;await tick();assert.doesNotMatch(panel.text(),/2026-11-19/);assert.equal(panel.open,false);
 console.log('PASS notification prefetch, shared request, synchronous cache, TTL, mutation/socket/cross-tab invalidation, retry, closed panel and account isolation');
})().catch(e=>{console.error(e);process.exitCode=1});
