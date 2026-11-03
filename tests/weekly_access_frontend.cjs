const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{constructor(){this.hidden=false;this.textContent='';this.children=[];this.attrs={};this.events={};}replaceChildren(...items){this.children=items;}append(...items){this.children.push(...items);}setAttribute(k,v){this.attrs[k]=v;}getAttribute(k){return this.attrs[k];}addEventListener(k,f){this.events[k]=f;}querySelector(){return null;}focus(){}}
async function setup({allowed=false,existing=false,failed=false}={}){
 const elements=new Map(),$=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};const calls=[];
 const json=async path=>{calls.push(path);if(path==='/study/weekly/latest'){if(existing)return {};throw Object.assign(new Error('empty'),{status:404});}if(failed)throw new Error('offline');return {features:allowed?['weekly']:[]};};
 const m={weekly:{id:1,period_start:'2026-11-03',period_end:'2026-11-09'},days:[{date:'2026-11-03'}],points:[],emotion:{},overall:{},keyword:{}};
 const exports={$ ,json,node:()=>new Element(),token:()=>1,owner:()=>1,expire:()=>{},chart:()=>new Element(),closeDetail:()=>{},weeklyModel:()=>m};
 const context=vm.createContext({window:{addEventListener:()=>{}},requestAnimationFrame:fn=>fn()});
 const stub=new vm.SyntheticModule(Object.keys(exports),function(){for(const [k,v]of Object.entries(exports))this.setExport(k,v);},{context});
 const module=new vm.SourceTextModule(fs.readFileSync('static/js/space/weekly.js','utf8'),{context});await module.link(()=>stub);await module.evaluate();await new Promise(resolve=>setImmediate(resolve));
 return {$,calls};
}
(async()=>{
 const free=await setup();assert(free.$('weekly-empty-title').textContent.includes('무료 이용 중에는'));assert(free.$('weekly-empty-copy').textContent.includes('이전에 받은'));assert.equal(free.$('weekly-empty-hint').hidden,true);
 const trial=await setup({allowed:true});assert(trial.$('weekly-empty-title').textContent.includes('조금만 더'));assert.equal(trial.$('weekly-empty-hint').hidden,false);
 const existing=await setup({existing:true});assert.equal(existing.$('weekly-empty').hidden,true);assert.deepEqual(existing.calls,['/study/weekly/latest']);assert(existing.$('weekly-period').textContent.includes('2026-11-03'));
 const failure=await setup({failed:true});assert(failure.$('weekly-status').textContent.includes('이용 상태를 확인하지 못했어요'));assert.equal(failure.$('weekly-retry').hidden,false);
 console.log('PASS weekly access UI: trial conditions, free empty state, existing result access, failed access lookup retry');
})().catch(e=>{console.error(e);process.exitCode=1;});
