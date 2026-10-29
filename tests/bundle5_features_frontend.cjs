const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('static/js/components/space/section.js','utf8');
let clicks=[],cards=[];
const makeCard=name=>({dataset:{},handlers:[],querySelector:()=>({textContent:name}),addEventListener(t,fn){this.handlers.push(fn)}});
const ctx=vm.createContext({window:{},document:{querySelectorAll:()=>cards,querySelector:s=>({click:()=>clicks.push(s)})}});
vm.runInContext(source,ctx);
for(let i=0;i<3;i++){
 cards=['대화하기','서재','텃밭','리포트'].map(makeCard);
 ctx.window.initSpaceSection();ctx.window.initSpaceSection();
 for(const card of cards){assert.equal(card.handlers.length,1);card.handlers[0]()}
}
assert.equal(clicks.length,12);assert.equal(clicks[4],'.main-tab[data-tab="chatting"]');
const {setup}=require('./bundle3_frontend.cjs');
(async()=>{
 const test=setup();
 const manager=test.window.globalNotificationManager || test.window.createNotificationManager();
 for(const type of ['report','final_report','plant_generation']){
  manager.storeNotification({type,report_id:999});assert.equal(manager.storedNotifications[type],undefined);
 }
 console.log('PASS features frontend: 3 space entries without duplicate handlers; 3 disabled notifications');
})().catch(e=>{console.error(e);process.exitCode=1});
