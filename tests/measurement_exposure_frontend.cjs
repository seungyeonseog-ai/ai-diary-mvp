const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
(async()=>{
 const calls=[],handlers={},storage=new Map(),observers=[];
 let who='a',fail=false;
 const document={visibilityState:'hidden',addEventListener:(name,fn)=>handlers[name]=fn};
 class Observer{constructor(fn){this.fn=fn;observers.push(this)}observe(el){this.el=el}disconnect(){this.disconnected=true}}
 const context=vm.createContext({document,IntersectionObserver:Observer,sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
  fetch:async(path,options)=>{calls.push([path,JSON.parse(options.body)]);return {ok:!fail}}});
 const ui=new vm.SyntheticModule(['owner','token'],function(){this.setExport('owner',()=>who);this.setExport('token',()=>who)},{context});
 const mod=new vm.SourceTextModule(fs.readFileSync('static/js/space/writing_analytics.js','utf8'),{context});await mod.link(()=>ui);await mod.evaluate();
 const m=mod.namespace,el={isConnected:true,hidden:false};
 m.observeLetterOpportunity(el,[4],'arrival');observers.at(-1).fn([{isIntersecting:true,intersectionRatio:1}]);assert.equal(calls.length,0);
 document.visibilityState='visible';handlers.visibilitychange();assert.equal(calls.length,1);assert.equal(calls[0][1].letter_id,4);
 m.observeLetterOpportunity(el,[4],'inbox');observers.at(-1).fn([{isIntersecting:true,intersectionRatio:1}]);assert.equal(calls.length,1);
 m.recordExtraOpportunity('w','2026-11-07','none');m.recordExtraOpportunity('w','2026-11-07','saved');m.recordExtraOpportunity('w','2026-11-07','saved');assert.equal(calls.length,3);
 who='b';m.observeLetterOpportunity(el,[4],'inbox');observers.at(-1).fn([{isIntersecting:true,intersectionRatio:1}]);assert.equal(calls.length,4);
 fail=true;m.recordExtraOpportunity('w','2026-11-08','saved');await new Promise(resolve=>setImmediate(resolve));fail=false;m.recordExtraOpportunity('w','2026-11-08','saved');assert.equal(calls.length,6);
 document.visibilityState='hidden';m.observeLetterOpportunity(el,[9],'arrival');observers.at(-1).fn([{isIntersecting:true,intersectionRatio:1}]);who='c';document.visibilityState='visible';handlers.visibilitychange();assert.equal(calls.length,6);
 console.log('PASS measurement exposure: hidden/visible, repeated surfaces, state/day/account dedup, failed delivery retry');
})().catch(e=>{console.error(e);process.exitCode=1});
