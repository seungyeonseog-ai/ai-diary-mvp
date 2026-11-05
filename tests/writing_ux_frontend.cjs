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
 const storage=new Map(),timers=new Map(),calls=[],navigation=[],dialogs=[],windowEvents=new Map();let seq=0,answer='cancel',identity='a',clockState=null,failSave=false;
 let diary={id:1,title:'원래 제목',body:'원래 본문',date:'2026-11-03',state:'draft',version:1,photos:[]};
 const copy=()=>JSON.parse(JSON.stringify(diary));
 async function json(path,options={}){
  calls.push([path,options]);
  if(clockState&&path==='/writing/test')return structuredClone(clockState);
  if(clockState&&path==='/writing'&&options.method==='POST')return {id:'today'};
  if(clockState&&path==='/writing/today')return {...structuredClone(clockState),id:'today',date:'2026-11-04',messages:[]};
  if(path.includes('/photos?')){assert.equal(Number(new URL('http://test'+path).searchParams.get('version')),diary.version);diary.photos.push({id:String(++seq),url:'/photo'});diary.version++;return {id:String(seq),version:diary.version}}
  if(path.includes('/photos/')){assert.equal(options.data.version,diary.version);diary.photos=diary.photos.filter(p=>!path.endsWith('/'+p.id));diary.version++;return {version:diary.version}}
  if(path.endsWith('/save')){if(failSave)throw Error('합성 저장 실패');assert.equal(options.data.version,diary.version);diary.state='saved';diary.version++;return copy()}
  if(path==='/writing/diaries/1'&&options.method==='DELETE'){diary.state='discarded';return {state:'discarded'}}
  if(options.method==='PATCH'){assert.equal(options.data.version,diary.version);Object.assign(diary,{title:options.data.title,body:options.data.body,version:diary.version+1});return copy()}
  if(path==='/writing/diaries/1')return copy();throw Error(path);
 }
 const context=vm.createContext({URL,URLSearchParams,AbortController,TextDecoder,setTimeout:f=>{const id=++seq;timers.set(id,f);return id},clearTimeout:id=>timers.delete(id),
  location:{search:'',assign:url=>navigation.push(url)},document:{visibilityState:'visible',querySelectorAll:()=>[],addEventListener(){}},
  window:{addEventListener:(name,fn)=>windowEvents.set(name,fn)},localStorage:{getItem:()=>''},sessionStorage:{get length(){return storage.size},key:i=>[...storage.keys()][i],getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  Intl,Date,Event:class{},console});
 context.URL.createObjectURL=()=> 'blob:test';context.URL.revokeObjectURL=()=>{};
 const exported={$ ,node:(tag,cls='',text='')=>Object.assign(new El(),{tag,className:cls,textContent:text}),id:()=>String(++seq),token:()=>identity,owner:()=>identity,json,
  request:async()=>({blob:async()=>({})}),readSSE:()=>{},dialog:async(...a)=>{dialogs.push(a);return answer},confirm:async(...a)=>{dialogs.push(a);return answer},toast:()=>{},logout:()=>{},expire:()=>{},safeNext:x=>x};
 const stub=new vm.SyntheticModule(Object.keys(exported),function(){for(const[k,v]of Object.entries(exported))this.setExport(k,v)},{context});
 const policy=new vm.SourceTextModule(fs.readFileSync('static/js/space/writing_policy.js','utf8'),{context});await policy.link(()=>{});await policy.evaluate();
 let source=fs.readFileSync('static/js/space/writing.js','utf8').replace("if(!token())void expire();else{void boot();connectNotifications();}",'');
 source+='\nexport {restore,updateActions,uploadPhotos,removePhoto,beginEdit,applyEdit,saveDiary,loadDiary,allowLeave,scheduleDiaryPrompt,cancelDiaryPrompt,requestLampReply};export function fixture(d,q={base_remaining:1,extra_remaining:2},operations=[]){state={id:"test",diary:d,messages:[],operations,quota:q}};export function stateDate(){return state.date}';
 const mod=new vm.SourceTextModule(source,{context});await mod.link(spec=>spec.includes('writing_policy')?policy:stub);await mod.evaluate();const m=mod.namespace;
 m.fixture(copy());await m.loadDiary();m.beginEdit({});$('edit-title').value='편집 중 제목';$('edit-body').value='편집 중 본문';
 answer='cancel';await $('cancel-edit').events.click[0]();assert.equal($('edit-form').hidden,false);assert.equal($('edit-body').value,'편집 중 본문');assert.equal(dialogs.at(-1)[0],'수정을 취소할까요?');assert.equal(dialogs.at(-1)[2].map(x=>x.label).join('/'),'네/아니요');
 answer='ok';await $('cancel-edit').events.click[0]();assert.equal($('edit-form').hidden,true);assert.equal(diary.body,'원래 본문');
 m.beginEdit({});$('edit-title').value='편집 중 제목';$('edit-body').value='편집 중 본문';
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
 answer='cancel';assert.equal(await m.allowLeave(),false);
 assert.deepEqual(JSON.parse(JSON.stringify(dialogs.at(-1)[2])),[{label:'저장하기',value:'save',primary:true},{label:'폐기하기',value:'discard'}]);
 assert.equal(dialogs.at(-1)[3].dismissible,false);
 answer='save';failSave=true;assert.equal(await m.allowLeave(),false);assert.equal($('error-panel').hidden,false);assert.equal($('edit-body').value,'편집 중 본문');failSave=false;
 assert.equal(await m.allowLeave(),false);assert.equal(diary.state,'saved');assert.equal(diary.title,'편집 중 제목');assert.equal(navigation.at(-1),'/library');assert.equal(storage.get('space:a:saved-book'),'1');
 await m.loadDiary();m.beginEdit({});
 await m.applyEdit();assert.equal(diary.title,'편집 중 제목');assert.equal(diary.body,'편집 중 본문');assert.equal(diary.state,'saved');assert.equal(diary.photos.length,3);assert.equal(navigation.at(-1),'/library');
 await m.loadDiary();assert.equal($('save-diary').hidden,true);assert.equal($('add-photo').hidden,true);assert.equal($('edit-diary').hidden,false);
 assert.equal(await m.allowLeave(),true);
 const saved=copy();diary.state='draft';m.fixture(copy());answer='discard';
 assert.equal(await m.allowLeave(),false);assert.equal(diary.state,'discarded');assert.equal(navigation.at(-1),'/space');
 assert.equal(calls.at(-1)[1].method,'DELETE');diary=saved;m.fixture(copy());
 await m.restore(true);assert.equal($('workspace').dataset.view,'chat');assert.equal($('diary-view').hidden,true);assert.equal($('make-diary').hidden,true);
 await m.restore();assert.equal($('workspace').dataset.view,'chat');
 m.fixture(copy(),{base_remaining:0,extra_remaining:2});$('message-input').value='추가 이야기';m.updateActions();assert.equal($('message-input').disabled,false);assert.equal($('lamp-submit').disabled,false);assert.equal($('make-diary').hidden,true);assert($('quota-label').textContent.includes('추가 2회'));
 assert.equal($('extra-quota-icon-1').dataset.lit,'true');assert.equal($('extra-quota-icon-2').dataset.lit,'true');
 assert($('quota-tooltip').textContent.includes('2번'));
 const lamps=['base-quota-icon','extra-quota-icon-1','extra-quota-icon-2'];
 for(let remaining=3;remaining>=0;remaining--){
  m.fixture(copy(),{base_remaining:remaining===3?1:0,extra_remaining:Math.min(remaining,2),features:['dialogue']});m.updateActions();
  assert.equal(lamps.map(id=>$(id).dataset.lit==='true'?'1':'0').join(''),'0'.repeat(3-remaining)+'1'.repeat(remaining));
 }
 m.fixture(copy(),{base_remaining:1,extra_remaining:0,features:[]});m.updateActions();
 assert.equal($('base-quota-icon').dataset.lit,'true');assert.equal($('extra-quota-icon-1').hidden,true);assert.equal($('extra-quota-icon-2').hidden,true);
 m.fixture(copy(),{base_remaining:0,extra_remaining:0});m.updateActions();assert.equal($('message-input').disabled,true);assert.equal($('lamp-submit').disabled,false);assert.equal($('lamp-submit').dataset.available,'false');assert.equal($('make-diary').hidden,true);
 for(const id of ['extra-quota-icon-1','extra-quota-icon-2']){assert.equal($(id).dataset.lit,'false');assert.equal($(id).hidden,false);}
 assert($('quota-tooltip').textContent.includes('모두 사용'));
 const beforeExhausted=calls.length;await m.requestLampReply();assert.equal(dialogs.at(-1)[0],'오늘 대화를 다 소진하셨어요');assert.equal(calls.length,beforeExhausted);
 m.fixture(copy(),{base_remaining:0,extra_remaining:1});$('message-input').value='아직 더 쓸 이야기';answer='more';const beforeMore=calls.length;
 await m.requestLampReply();assert.equal($('message-input').value,'아직 더 쓸 이야기');assert.equal(calls.length,beforeMore);assert.equal(dialogs.at(-1)[2][0].label,'다 말했어요, 답변받을래요');assert.equal(dialogs.at(-1)[2][1].label,'더 말할래요');
 m.fixture({...copy(),state:'draft'});m.updateActions();assert.equal($('make-diary').hidden,false);assert.equal($('make-diary').textContent,'작성 중인 일기 열기');
 m.fixture(null,{base_remaining:0,extra_remaining:0,features:[]},[{kind:'lamp',state:'succeeded',request_id:'reply-1'}]);
 $('message-input').value='';storage.set('space:a:test:diary-prompt','"reply-1"');m.updateActions();
 assert.equal($('make-diary').hidden,true);assert.equal($('lamp-submit').disabled,false);
 answer='more';const beforeDiaryPrompt=calls.length;await m.requestLampReply();
 assert.equal(dialogs.at(-1)[0],'이 이야기로 일기를 만들까요?');assert.equal(calls.length,beforeDiaryPrompt);
 assert.equal(policy.namespace.replyReadingDelay('짧음'),5000);assert.equal(policy.namespace.replyReadingDelay('가'.repeat(1000)),15000);
 m.fixture(null);m.scheduleDiaryPrompt('답변');assert.equal(timers.size,1);m.cancelDiaryPrompt();assert.equal(timers.size,0);
 m.fixture(null);$('workspace').dataset.view='chat';$('message-input').value='날짜가 바뀌어도 보존할 입력';
 clockState={id:'test',date:'2026-11-03',server_now:'2026-11-04T00:00:01+09:00',state:'active',messages:[],operations:[],diary:null,quota:{base_remaining:1,extra_remaining:2}};
 await windowEvents.get('daily:clock')();assert.equal(m.stateDate(),'2026-11-04');assert.equal($('message-input').value,'날짜가 바뀌어도 보존할 입력');
 clockState=null;m.scheduleDiaryPrompt('답변');const beforeIdentityChange=dialogs.length;identity='b';await [...timers.values()][0]();assert.equal(dialogs.length,beforeIdentityChange);
 console.log('PASS writing UX: photo limit persistence/reset, editing text/version preservation, cancel, saved detail navigation, reading timer cancellation and account guard');
})().catch(e=>{console.error(e);process.exitCode=1});
