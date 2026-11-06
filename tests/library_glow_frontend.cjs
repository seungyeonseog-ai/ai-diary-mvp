const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('static/js/space/library.js','utf8');
for(const action of ['timeout','click','auxclick']){
 const nodes=new Map(),timers=new Map(),stored=new Map([['space:1:saved-book','1']]);
 function node(){const classes=new Set();return {children:[],listeners:{},classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x)},append(...x){this.children.push(...x)},replaceChildren(){this.children=[]},addEventListener(event,handler){this.listeners[event]=handler}};}
 const $=key=>{if(!nodes.has(key))nodes.set(key,node());return nodes.get(key)};
 const context=vm.createContext({$,node,uid:'1',today:'2026-11-06',shelfBooks:x=>x,linkDiary(){},cover:()=>'/cover.webp',dateLabel:x=>x,libraryURL:()=>'/library',sessionStorage:{getItem:k=>stored.get(k),removeItem:k=>stored.delete(k)},setTimeout(fn,ms){timers.set(1,{fn,ms});return 1},clearTimeout:id=>timers.delete(id)});
 vm.runInContext(source.slice(source.indexOf('function renderShelf('),source.indexOf('function renderMonth('))+'\nrenderShelf({books:[{id:1,state:"saved",title:"synthetic",date:"2026-11-06"}],total:1,page:1,pages:1});',context);
 const book=$('books').children[0];assert.ok(book.classList.contains('just-saved'));assert.equal(timers.get(1).ms,6000);
 if(action==='timeout')timers.get(1).fn();else{book.listeners[action]();assert.equal(timers.size,0)}
 assert.ok(!book.classList.contains('just-saved'));assert.equal(stored.size,0);
}
console.log('PASS saved glow: six seconds, click/middle-click stop, arrival consumed once');
