const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class El{
 constructor(){this.children=[];this.events={};this.hidden=false;this.disabled=false;this.value='';this.textContent='';this.dataset={};this.style={};}
 append(...a){this.children.push(...a)}replaceChildren(...a){this.children=a;this.textContent=''}
 addEventListener(k,f){(this.events[k]??=[]).push(f)}setAttribute(k,v){this[k]=v}focus(){}
 querySelectorAll(tag){return this.children.flatMap(c=>[...(c.tag===tag?[c]:[]),...c.querySelectorAll(tag)])}
 querySelector(){return new El()}
}
(async()=>{
 const ids=new Map();const $=id=>{if(!ids.has(id))ids.set(id,new El());return ids.get(id)};
 const storage=new Map(),timers=new Map(),calls=[],navigation=[],dialogs=[];let seq=0,answer='cancel',identity='a';
 let diary={id:1,title:'원래 제목',body:'원래 본문',date:'2026-11-03',state:'draft',version:1,photos:[]};
 const copy=()=>JSON.parse(JSON.stringify(diary));
 async function json(path,options={}){
  calls.push([path,options]);
  if(path.includes('/photos?')){assert.equal(Number(new URL('http://test'+path).searchParams.get('version')),diary.version);diary.photos.push({id:String(++seq),url:'/photo'});diary.version++;return {id:String(seq),version:diary.version}}
  if(path.includes('/photos/')){assert.equal(options.data.version,diary.version);diary.photos=diary.photos.filter(p=>!path.endsWith('/'+p.id));diary.version++;return {version:diary.version}}
  if(path.endsWith('/save')){diary.state='saved';diary.version++;return copy()}
  if(options.method==='PATCH'){assert.equal(options.data.version,diary.version);Object.assign(diary,{title:options.data.title,body:options.data.body,version:diary.version+1});return copy()}
  if(path==='/writing/diaries/1')return copy();throw Error(path);
 }
 const context=vm.createContext({URL,URLSearchParams,AbortController,TextDecoder,setTimeout:f=>{const id=++seq;timers.set(id,f);return id},clearTimeout:id=>timers.delete(id),
  location:{search:'',assign:url=>navigation.push(url)},document:{visibilityState:'visible',querySelectorAll:()=>[],addEventListener(){}},
  window:{addEventListener(){}},localStorage:{getItem:()=>''},sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  Intl,Date,Event:class{},console});
 context.URL.createObjectURL=()=> 'blob:test';context.URL.revokeObjectURL=()=>{};
 const exported={$ ,node:(tag,cls='',text='')=>Object.assign(new El(),{tag,className:cls,textContent:text}),id:()=>String(++seq),token:()=>identity,owner:()=>identity,json,
  request:async()=>({blob:async()=>({})}),readSSE:()=>{},dialog:async(...a)=>{dialogs.push(a);return answer},confirm:async(...a)=>{dialogs.push(a);return answer},toast:()=>{},logout:()=>{},expire:()=>{},safeNext:x=>x};
 const stub=new vm.SyntheticModule(Object.keys(exported),function(){for(const[k,v]of Object.entries(exported))this.setExport(k,v)},{context});
 const policy=new vm.SourceTextModule(fs.readFileSync('static/js/space/writing_policy.js','utf8'),{context});await policy.link(()=>{});await policy.evaluate();
 let source=fs.readFileSync('static/js/space/writing.js','utf8').replace("if(!token())void expire();else{void boot();connectNotifications();}",'');
 source+='\nexport {restore,uploadPhotos,removePhoto,beginEdit,applyEdit,saveDiary,loadDiary,allowLeave,scheduleDiaryPrompt,cancelDiaryPrompt};export function fixture(d){state={id:"test",diary:d,messages:[],operations:[],quota:{base_remaining:1,extra_remaining:2}}}';
 const mod=new vm.SourceTextModule(source,{context});await mod.link(spec=>spec.includes('writing_policy')?policy:stub);await mod.evaluate();const m=mod.namespace;
 m.fixture(copy());await m.loadDiary();m.beginEdit({});$('edit-title').value='편집 중 제목';$('edit-body').value='편집 중 본문';
 const entries=Array.from({length:4},(_,i)=>({id:'p'+i,file:{name:'합성'+i+'.png',size:10}}));
 await m.uploadPhotos(entries);
 assert.equal(diary.photos.length,3);assert.equal(calls.filter(([p])=>p.includes('/photos?')).length,3);
 assert.equal($('edit-title').value,'편집 중 제목');assert.equal($('edit-body').value,'편집 중 본문');assert.equal($('edit-form').hidden,false);
 assert.equal($('add-photo').disabled,false);assert.equal($('edit-diary').hidden,true);assert.equal($('discard-diary').hidden,true);assert.equal($('save-diary').hidden,true);
 assert.equal($('photo-errors').querySelectorAll('button').length,0);assert.equal($('photo-errors').children.length,1);
 answer='cancel';await m.removePhoto(diary.photos[0].id);assert.equal(diary.photos.length,3);assert.equal($('photo-errors').children.length,1);
 answer='ok';await m.removePhoto(diary.photos[0].id);assert.equal(diary.photos.length,2);assert.equal($('photo-errors').children.length,0);
 await m.uploadPhotos([{id:'next',file:{name:'다음.png',size:10}}]);assert.equal(diary.photos.length,3);assert.equal($('photo-errors').children.length,0);
 await m.uploadPhotos([{id:'over',file:{name:'초과.png',size:10}}]);assert.equal($('photo-errors').children.length,1);
 answer='cancel';assert.equal(await m.allowLeave(),false);assert(dialogs.at(-1)[1].includes('저장되지'));
 await m.applyEdit();assert.equal(diary.title,'편집 중 제목');assert.equal(diary.body,'편집 중 본문');assert.equal(diary.state,'saved');assert.equal(diary.photos.length,3);assert(navigation.at(-1).startsWith('/diary/1?'));
 await m.loadDiary();assert.equal($('save-diary').hidden,true);assert.equal($('add-photo').hidden,true);assert.equal($('edit-diary').hidden,false);
 assert.equal(await m.allowLeave(),true);
 await m.restore(true);assert.equal($('workspace').dataset.view,'chat');assert.equal($('diary-view').hidden,true);assert.equal($('make-diary').textContent,'오늘 일기 보기');
 await m.restore();assert.equal($('workspace').dataset.view,'chat');
 assert.equal(policy.namespace.replyReadingDelay('짧음'),5000);assert.equal(policy.namespace.replyReadingDelay('가'.repeat(1000)),15000);
 m.fixture(null);m.scheduleDiaryPrompt('답변');assert.equal(timers.size,1);m.cancelDiaryPrompt();assert.equal(timers.size,0);
 m.scheduleDiaryPrompt('답변');identity='b';await [...timers.values()][0]();assert.equal(dialogs.at(-1)[0],'저장하지 않고 나갈까요?');
 console.log('PASS writing UX: photo limit persistence/reset, editing text/version preservation, cancel, saved detail navigation, reading timer cancellation and account guard');
})().catch(e=>{console.error(e);process.exitCode=1});
