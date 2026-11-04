const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element extends EventTarget{
 constructor(){super();this.children=[];this.hidden=false;this.attributes={};this.open=false;this.returnValue='';Object.defineProperty(this,'id',{set:value=>elements.set(value,this)});}
 append(...children){this.children.push(...children)}
 replaceChildren(){this.children=[]}
 setAttribute(name,value){this.attributes[name]=value}
 querySelector(){return close}
 showModal(){this.open=true}
 close(value=''){this.returnValue=value;this.open=false;this.dispatchEvent(new Event('close'))}
}
const close=new Element(),elements=new Map();let createMissing=true;const $=id=>{if(!elements.has(id)&&createMissing)elements.set(id,new Element());return elements.get(id)||null};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const context=vm.createContext({URL,Event,AbortSignal,crypto:require('node:crypto').webcrypto,setTimeout,clearTimeout,
  document:{getElementById:$,createElement:()=>new Element(),body:new Element()},window:{addEventListener(){}},
  localStorage:{getItem:()=>null},sessionStorage:{length:0},location:{origin:'http://localhost'},console});
 const module=new vm.SourceTextModule(fs.readFileSync('static/js/space/ui.js','utf8'),{context});await module.link(()=>{});await module.evaluate();
 const ui=module.namespace,el=$('ui-dialog');
 const required=ui.dialog('필수 단계','안내',[{label:'다음',value:'next',primary:true}],{dismissible:false});await tick();
 assert.equal(close.hidden,true);assert.equal(el.attributes.closedby,'none');
 const cancel=new Event('cancel',{cancelable:true});assert.equal(el.dispatchEvent(cancel),false);
 const escape=new Event('keydown',{cancelable:true});Object.defineProperty(escape,'key',{value:'Escape'});assert.equal(el.dispatchEvent(escape),false);
 const normal=ui.dialog('다음 알림','');await tick();assert.equal($('dialog-title').textContent,'필수 단계');
 el.close('next');assert.equal(await required,'next');await tick();
 assert.equal($('dialog-title').textContent,'다음 알림');assert.equal(close.hidden,false);assert.equal($('dialog-description').hidden,true);
 assert.equal(el.attributes.closedby,'closerequest');assert.equal(el.dispatchEvent(new Event('cancel',{cancelable:true})),true);
 el.close();assert.equal(await normal,'cancel');
 elements.clear();createMissing=false;const legacy=ui.dialog('캐시된 가입 화면','알림 마크업 자동 준비');await tick();
 assert.equal($('ui-dialog').open,true);assert.equal($('dialog-title').textContent,'캐시된 가입 화면');$('ui-dialog').close('ok');assert.equal(await legacy,'ok');
 // 이전 HTML은 type=module 없이 register.js를 로드한다.
 new vm.Script(fs.readFileSync('static/js/register.js','utf8'));
 console.log('PASS shared dialog: required guards, queue, dismissal restored, missing markup and legacy classic registration script');
})().catch(error=>{console.error(error);process.exitCode=1});
