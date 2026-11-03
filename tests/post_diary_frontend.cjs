const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class El{constructor(){this.children=[];this.events={};this.hidden=false;this.disabled=false;this.value='';this.textContent='';this.dataset={};this.style={}}append(...a){this.children.push(...a)}replaceChildren(){this.children=[]}addEventListener(k,f){this.events[k]=f}setAttribute(){}focus(){}querySelectorAll(){return []}}
(async()=>{
 const elements=new Map(),calls=[],navigation=[],dialogs=[];$=id=>{if(!elements.has(id))elements.set(id,new El());return elements.get(id)};
 let data=null;
 const context=vm.createContext({URL,URLSearchParams,AbortController,Intl,Date,console,setTimeout:()=>1,clearTimeout(){},
  location:{search:'',assign:url=>navigation.push(url)},document:{visibilityState:'visible',querySelectorAll:()=>[],addEventListener(){}},window:{addEventListener(){}},
  localStorage:{getItem:()=>''},sessionStorage:{length:0,getItem:()=>null,setItem(){},removeItem(){}}});
 const ui={$ ,node:()=>new El(),id:()=> 'test',token:()=> 'same',owner:()=> '1',json:async path=>{calls.push(path);return structuredClone(data)},request:async()=>{},readSSE:async()=>{},
  dialog:async()=>{dialogs.push('dialog');return 'cancel'},confirm:async()=>{dialogs.push('confirm');return 'cancel'},toast(){},logout(){},expire(){},safeNext:x=>x};
 const stub=new vm.SyntheticModule(Object.keys(ui),function(){for(const[k,v]of Object.entries(ui))this.setExport(k,v)},{context});
 const policy=new vm.SourceTextModule(fs.readFileSync('static/js/space/writing_policy.js','utf8'),{context});await policy.link(()=>{});await policy.evaluate();
 let source=fs.readFileSync('static/js/space/writing.js','utf8').replace("if(!token())void expire();else{void boot();connectNotifications();}",'');
 source+='\nexport {updateActions,sendLamp};export function fixtureState(value){state=value;busy=false}';
 const module=new vm.SourceTextModule(source,{context});await module.link(spec=>spec.includes('writing_policy')?policy:stub);await module.evaluate();const api=module.namespace;
 const make=(remaining,operations=[{kind:'lamp',state:'succeeded',source_ids:[1]}])=>({id:'test',date:'2026-11-03',server_now:'2026-11-03T12:00:00+09:00',diary:{id:1,state:'saved'},messages:[{id:1,role:'user',message:'합성'}],operations,quota:{base_remaining:0,extra_remaining:remaining}});
 data=make(2);api.fixtureState(data);api.updateActions();assert.equal($('message-input').disabled,false);assert.equal($('continue-chat').hidden,false);assert.equal($('continue-chat').textContent,'전등이와 더 이야기하기');
 await $('make-diary').events.click();assert(navigation[0].startsWith('/diary/1?'));assert.equal(calls.length,0);
 api.fixtureState(make(0));api.updateActions();assert.equal($('message-input').disabled,true);assert.equal($('lamp-submit').disabled,true);assert.equal($('continue-chat').hidden,true);assert.equal($('make-diary').hidden,false);
 api.fixtureState(make(2,[]));api.updateActions();assert.equal($('continue-chat').hidden,false);
 data=make(1);api.fixtureState(data);$('message-input').value='';await api.sendLamp();assert.equal(dialogs.length,0);assert(calls.every(path=>!path.includes('/generate/')));
 console.log('PASS post-diary UI: remaining input, cached diary navigation, exhaustion, legacy diary, empty lamp does not regenerate');
})().catch(error=>{console.error(error);process.exitCode=1});
