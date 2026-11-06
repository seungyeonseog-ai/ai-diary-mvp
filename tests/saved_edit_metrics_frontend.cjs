// 실제 모듈의 수정 진입/자동 복원/중복/계정 변경 검사. 외부 통신 없음.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function scenario({linked=true,restore=false,fail=false}={}){
 const elements=new Map(),storage=new Map(),events=[];let user='1';
 const $=key=>{if(!elements.has(key))elements.set(key,{dataset:{},value:'',hidden:false,
  addEventListener(){},setAttribute(){},focus(){},querySelectorAll(){return []}});return elements.get(key)};
 $('workspace').dataset.diaryId='1';
 const context=vm.createContext({URLSearchParams,URL,console,clearTimeout(){},setTimeout(){},
  location:{search:linked?'?navigation=navigation-id&visit=visit-id':''},
  document:{querySelectorAll:()=>[],addEventListener(){},visibilityState:'visible'},window:{addEventListener(){}},
  sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  fetch:async(_path,options)=>{events.push(JSON.parse(options.body));return {ok:!fail}}});
 const exports={$ ,id:()=> 'id',owner:()=>user,token:()=>user,safeNext:x=>x,
  node(){},json(){},request(){},readSSE(){},dialog(){},confirm(){},toast(){},logout(){},expire(){}};
 const ui=new vm.SyntheticModule(Object.keys(exports),function(){for(const[k,v]of Object.entries(exports))this.setExport(k,v)},{context});
 const policy=new vm.SourceTextModule(fs.readFileSync('static/js/space/writing_policy.js','utf8'),{context});await policy.link(()=>{});
 const analytics=new vm.SourceTextModule(fs.readFileSync('static/js/space/writing_analytics.js','utf8'),{context});await analytics.link(()=>ui);
 let source=fs.readFileSync('static/js/space/writing.js','utf8').replace('if(!token())void expire();else{void boot();connectNotifications();}','');
 source+='\nexport {beginEdit};export function reset(){editing=false;state={id:"writing-id",diary:{id:1,state:"saved",title:"synthetic",body:"synthetic",version:1}}}';
 const module=new vm.SourceTextModule(source,{context});await module.link(s=>s.includes('writing_policy')?policy:s.includes('writing_analytics')?analytics:ui);await module.evaluate();
 module.namespace.reset();module.namespace.beginEdit({restore});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal($('edit-form').hidden,false);
 const expected=linked&&!restore?1:0;assert.equal(events.length,expected);
 if(expected)assert.deepEqual(events[0],{event:'saved_diary_edit_opened',diary_id:1,navigation_id:'navigation-id',visit_id:'visit-id'});
 module.namespace.reset();module.namespace.beginEdit({restore});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(events.length,fail?expected*2:expected);
 const before=events.length;user='2';module.namespace.reset();module.namespace.beginEdit();
 assert.equal(events.length,before);
}
(async()=>{await scenario();await scenario({restore:true});await scenario({linked:false});await scenario({fail:true});console.log('PASS saved edit: linked IDs, once per detail, restore/direct excluded, failed delivery retry, account guard');})().catch(e=>{console.error(e);process.exitCode=1});
