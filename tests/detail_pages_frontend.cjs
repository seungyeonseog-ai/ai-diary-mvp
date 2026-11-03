const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(tag,cls='',text=''){this.tag=tag;this.className=cls;this.textContent=text;this.children=[];this.events={};this.attrs={};this.hidden=false;this.disabled=false;}
 append(...els){this.children.push(...els)}replaceChildren(...els){this.children=els;this.textContent=''}setAttribute(k,v){this.attrs[k]=v}addEventListener(k,fn){(this.events[k]??=[]).push(fn)}focus(){}
 querySelectorAll(tag){return this.children.flatMap(c=>[...(c.tag===tag?[c]:[]),...c.querySelectorAll(tag)])}
 set innerHTML(v){throw Error('Unsafe HTML write')}
 async click(){for(const fn of this.events.click||[])await fn({})}
 text(){return this.textContent+this.children.map(c=>c.text()).join(' ')}
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function setup({letter=true,search=''}={}){
 const ids=Object.fromEntries(['letter-content','daily-inbox-status','letter-page-error','daily-inbox','daily-archive','letter-page-panel'].map(k=>[k,new Element('div')]));
 let identity='one',saved=false,confirmResult='cancel',defer=null;const calls=[],listeners={},documentEvents={};
 const request=async(path,options={})=>{calls.push([path,options.method||'GET']);if(defer&&path==='/daily/inbox')return defer;
  if(path==='/daily/inbox')return {server_date:'2026-11-03',state:letter?'ready':'waiting_time',hour:22,letter:letter?{id:1,saved}:null};
  if(path==='/daily/letters?view=archive')return {items:saved?[{id:1,date:'2026-11-03'}]:[]};
  if(path==='/daily/letters/1')return {id:1,date:'2026-11-03',body:'<script> literal body',saved,archive_deleted:false};
  if(path==='/daily/letters/1/save'){saved=true;return {ok:true}}if(path==='/daily/letters/1/view')return {ok:true};
  throw Error('Unexpected request '+path);
 };
 const context=vm.createContext({URLSearchParams,history:{replaceState:()=>{}},location:{search},document:{getElementById:k=>ids[k],createElementNS:(ns,tag)=>new Element(tag),addEventListener:(k,fn)=>documentEvents[k]=fn},window:{addEventListener:(k,fn)=>listeners[k]=fn,dispatchEvent:()=>{}},Event:class{}});
 const exports={$:k=>ids[k],json:request,node:(tag,cls,text)=>new Element(tag,cls,text),token:()=>identity,owner:()=>identity,confirm:async()=>confirmResult,expire:()=>{}};
 const stub=new vm.SyntheticModule(Object.keys(exports),function(){for(const [k,v]of Object.entries(exports))this.setExport(k,v);},{context});
 const module=new vm.SourceTextModule(fs.readFileSync('static/js/space/letters.js','utf8'),{context});await module.link(()=>stub);await module.evaluate();await flush();await flush();
 return {ids,calls,listeners,change:()=>identity='two',setDeferred:p=>defer=p,confirm:v=>confirmResult=v};
}
(async()=>{
 const a=await setup();assert(a.ids['letter-content'].text().includes('<script> literal body'));assert.equal(a.ids['letter-content'].querySelectorAll('dialog').length,0);
 const save=a.ids['letter-content'].querySelectorAll('button').find(b=>b.textContent==='보관함에 저장');await Promise.all([save.click(),save.click()]);await flush();assert.equal(a.calls.filter(([p])=>p==='/daily/letters/1/save').length,1);assert(a.ids['letter-content'].text().includes('보관한 편지예요.'));
 await a.ids['daily-archive'].click();await a.ids['letter-content'].querySelectorAll('button')[0].click();assert(a.ids['letter-content'].text().includes('literal body'));
 const del=a.ids['letter-content'].querySelectorAll('button').find(b=>b.textContent==='보관함에서 삭제');await del.click();assert(!a.calls.some(([p])=>p.endsWith('archive-delete')));
 const received=await setup({search:'?letter=1'});assert.equal(received.ids['daily-inbox'].textContent,'받은편지');assert(received.ids['letter-content'].text().includes('literal body'));
 const b=await setup({letter:false});assert(b.ids['letter-content'].text().includes('아직 도착한 응원 편지가 없어요.'));assert(!b.ids['letter-content'].text().includes('literal body'));
 let resolve;b.setDeferred(new Promise(r=>resolve=r));const pending=b.ids['daily-inbox'].click();await flush();await b.ids['daily-archive'].click();resolve({server_date:'2026-11-03',state:'ready',hour:22,letter:{id:1}});await pending;await flush();assert(b.ids['letter-content'].text().includes('아직 보관한 편지가 없어요.'));
 const c=await setup();let finish;c.setDeferred(new Promise(r=>finish=r));const load=c.ids['daily-inbox'].click();await flush();c.change();c.listeners['space:identity-cleared']();finish({server_date:'2026-11-03',state:'ready',hour:22,letter:{id:1}});await load;await flush();assert.equal(c.ids['letter-content'].text(),'');
 console.log('PASS detail pages: inline safe body, save/archive reread, cancel via dismiss, empty state, stale tab response and account change isolation');
})().catch(e=>{console.error(e);process.exitCode=1});
