const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(){this.value='';this.textContent='';this.children=[];this.dataset={};this.style={};this.disabled=false;this.hidden=false;}
 addEventListener(){}setAttribute(){}focus(){}append(...items){this.children.push(...items)}replaceChildren(){this.children=[]}querySelectorAll(){return []}
}
async function fixture(){
 const elements=new Map(),events=new Map(),storage=new Map(),calls=[];
 const $=key=>{if(!elements.has(key))elements.set(key,new Element());return elements.get(key)};
 $('workspace').dataset.view='chat';
 const sessionStorage={get length(){if(failStorageAccess)throw Error('synthetic storage denied');return storage.size},key:i=>[...storage.keys()][i],getItem:k=>storage.get(k)??null,setItem:(k,v)=>{if(failDraftSave&&k==='space:1:today:composer')throw Error('synthetic storage full');storage.set(k,v)},removeItem:k=>storage.delete(k)};
 const server=new Map();let target='today',failStart=false,failDraftSave=false,failStorageAccess=false;
 async function json(path,options={}){calls.push(path);if(path==='/writing'&&options.method==='POST'){if(failStart)throw Error('synthetic outage');return {id:target}};if(server.has(path))return structuredClone(server.get(path));throw Error('unexpected '+path)}
 const context=vm.createContext({URL,URLSearchParams,AbortController,TextDecoder,Intl,Date,console,
  document:{visibilityState:'visible',querySelectorAll:()=>[],addEventListener(){}},window:{addEventListener:(key,fn)=>events.set(key,fn)},
  location:{search:'',assign(){}},localStorage:{getItem:()=>''},sessionStorage,setTimeout:()=>1,clearTimeout(){},Event:class{}});
 const ui={$ ,node:()=>new Element(),id:()=> 'synthetic',token:()=> 'identity',owner:()=> '1',json,request:async()=>{},readSSE:async()=>{},dialog:async()=> 'cancel',confirm:async()=> 'cancel',toast(){},logout(){},expire(){},safeNext:x=>x};
 const stub=new vm.SyntheticModule(Object.keys(ui),function(){for(const [key,value] of Object.entries(ui))this.setExport(key,value)},{context});
 const policy=new vm.SourceTextModule(fs.readFileSync('static/js/space/writing_policy.js','utf8'),{context});await policy.link(()=>{});await policy.evaluate();
 let source=fs.readFileSync('static/js/space/writing.js','utf8').replace("if(!token())void expire();else{void boot();connectNotifications();}",'');
 source+='\nexport {restoreDayComposer,renderChat,updateActions,ensureToday};export function fixtureState(value){state=value;busy=false;editing=false}export function stateId(){return state.id}export function pause(){busy=true}';
 const module=new vm.SourceTextModule(source,{context});await module.link(spec=>spec.includes('writing_policy')?policy:stub);await module.evaluate();
 return {$,events,storage,calls,server,api:module.namespace,failStart:()=>{failStart=true},failDraftSave:()=>{failDraftSave=true},failStorageAccess:()=>{failStorageAccess=true}};
}
const old=()=>({id:'old',date:'2026-11-09',server_now:'2026-11-09T23:59:59+09:00',state:'active',diary:null,messages:[{id:1,role:'gpt',message:'합성 답변'}],operations:[],quota:{base_remaining:0,extra_remaining:2}});
const today=()=>({...old(),id:'today',date:'2026-11-10',server_now:'2026-11-10T00:00:00+09:00',messages:[],quota:{base_remaining:1,extra_remaining:0}});
(async()=>{
 let f=await fixture();f.api.fixtureState(old());f.$('message-input').value='입력 보존';
 f.server.set('/writing/old',{...old(),server_now:today().server_now,quota:{base_remaining:0,extra_remaining:0}});f.server.set('/writing/today',today());
 await f.events.get('daily:clock')();assert.equal(f.api.stateId(),'today');assert.equal(f.$('message-input').value,'입력 보존');assert.equal(f.$('message-input').disabled,false);

 f=await fixture();f.api.fixtureState(old());f.server.set('/writing/old',{...old(),quota:{base_remaining:0,extra_remaining:0}});
 await f.events.get('daily:clock')();assert.equal(f.$('message-input').disabled,true);assert.equal(f.$('lamp-submit').disabled,true);

 f=await fixture();f.api.fixtureState(today());f.storage.set('space:1:composer-resume',JSON.stringify({id:'old',date:'2026-11-09',text:'자정 새로고침 입력'}));
 await f.api.restoreDayComposer();f.api.renderChat();assert.equal(f.$('message-input').value,'자정 새로고침 입력');

 f=await fixture();f.api.fixtureState(today());f.storage.set('space:1:old:composer',JSON.stringify('구형 화면의 입력'));f.server.set('/writing/old',old());
 await f.api.restoreDayComposer();f.api.renderChat();assert.equal(f.$('message-input').value,'구형 화면의 입력');assert.deepEqual(f.calls,['/writing/old']);assert.equal(f.storage.has('space:1:old:composer'),false);
 f.storage.delete('space:1:today:composer');f.storage.delete('space:1:composer-resume');await f.api.restoreDayComposer();assert.equal(f.storage.has('space:1:today:composer'),false);

 f=await fixture();f.api.fixtureState(today());f.storage.set('space:1:old:composer',JSON.stringify('저장 공간 오류에도 보관'));f.server.set('/writing/old',old());f.failDraftSave();
 await f.api.restoreDayComposer();assert.equal(f.storage.get('space:1:old:composer'),JSON.stringify('저장 공간 오류에도 보관'));

 f=await fixture();f.api.fixtureState(today());f.failStorageAccess();await f.api.restoreDayComposer();assert.equal(f.calls.length,0);

 f=await fixture();f.api.fixtureState(today());f.storage.set('space:2:foreign:composer',JSON.stringify('타계정 합성 입력'));
 await f.api.restoreDayComposer();assert.equal(f.calls.length,0);assert.equal(f.storage.has('space:1:today:composer'),false);

 f=await fixture();f.api.fixtureState(old());f.$('message-input').value='연결 실패에도 유지';f.storage.set('space:1:old:composer',JSON.stringify('연결 실패에도 유지'));
 f.server.set('/writing/old',{...old(),server_now:today().server_now});f.failStart();
 await assert.rejects(()=>f.api.ensureToday());assert.equal(f.storage.get('space:1:old:composer'),JSON.stringify('연결 실패에도 유지'));assert.equal(f.$('message-input').value,'연결 실패에도 유지');

 f=await fixture();f.api.fixtureState(old());f.api.pause();await f.events.get('daily:clock')();assert.equal(f.calls.length,0);
 console.log('PASS 9 expiry UI checks: open page, exhausted lamp, midnight reload, legacy cleanup, storage write/access failure, account isolation, outage preservation, busy guard');
})().catch(error=>{console.error(error);process.exitCode=1});
