const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
(async()=>{
 for(const search of ['', '?next=%2Fspace','?next=%2Flibrary','?next=https://example.org']){
  let submit,destination,cleared=false;const stored=new Map();
  const button={disabled:false},error={textContent:''};
  const elements={loginForm:{addEventListener(name,fn){submit=fn},querySelector(){return button}},'login-error':error,username:{value:'synthetic'},password:{value:'test-only'},rememberId:{checked:false}};
  const context=vm.createContext({document:{getElementById:id=>elements[id]},localStorage:{getItem:k=>stored.get(k),setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)},location:{search,assign:v=>destination=v},fetch:async()=>({ok:true,json:async()=>({access_token:'isolated',nickname:'합성',user_id:2})}),TypeError,Error});
  const ui=new vm.SyntheticModule(['clearIdentity'],function(){this.setExport('clearIdentity',()=>{cleared=true})},{context});
  const login=new vm.SourceTextModule(fs.readFileSync('static/js/space/login.js','utf8'),{context});await login.link(()=>ui);await login.evaluate();
  await submit({preventDefault(){}});assert.equal(destination,'/');assert.ok(cleared);assert.equal(stored.get('user_id'),'2');assert.equal(button.disabled,false);assert.equal(error.textContent,'');
  destination=undefined;context.fetch=async()=>({ok:false,json:async()=>({detail:'합성 로그인 실패'})});await submit({preventDefault(){}});assert.equal(destination,undefined);assert.equal(error.textContent,'합성 로그인 실패');
 }
 console.log('PASS login: success returns main for direct/space/library/external next; failed login stays with error');
})().catch(error=>{console.error(error);process.exitCode=1});
