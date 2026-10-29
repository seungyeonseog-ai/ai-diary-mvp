const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const boxes=new Map();
function element(){return {children:[],style:{},append(...x){this.children.push(...x)},replaceChildren(...x){this.children=x}}}
for(const c of ['top-box','middle-box','bottom-box']) boxes.set(`.constellation-report-box.${c}`,element());
const logs=[], marker='<img src=x onerror="throw 1">\nsynthetic-private';
const context=vm.createContext({window:{},console:{log:(...x)=>logs.push(x),error:(...x)=>logs.push(x)},document:{querySelector:s=>boxes.get(s),createElement:element}});
vm.runInContext(fs.readFileSync('static/js/components/constellation/report.js','utf8'),context);
context.renderPersonalityReport({emotional_pattern:marker,personality_tendency:marker,unconscious_insight:marker});
for(const b of boxes.values()) {assert.equal(b.children[0].children[1].textContent,marker);assert.equal(b.children[0].children[1].innerHTML,undefined)}
assert.equal(logs.length,0);
const base=fs.readFileSync('templates/base.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
(async()=>{for(const mode of ['ok','401','network','no-token']){
 const store=new Map(mode==='no-token'?[]:[['access_token','synthetic-token'],['user_id','999']]);let calls=0;
 const ctx=vm.createContext({window:{},AbortSignal,localStorage:{getItem:k=>store.get(k),clear:()=>store.clear()},document:{getElementById:()=>({style:{}})},fetch:async(u,o)=>{calls++;assert.equal(u,'/logout');assert.equal(o.headers.Authorization,'Bearer synthetic-token');assert.equal(o.body,undefined);if(mode==='network')throw Error('network');return {status:mode==='401'?401:200}}});
 vm.runInContext(base,ctx);await ctx.logout();assert.equal(store.size,0);assert.equal(calls,mode==='no-token'?0:1);
}console.log('PASS security frontend: safe text rendering/logs and 4 logout paths');})().catch(e=>{console.error(e);process.exitCode=1});
