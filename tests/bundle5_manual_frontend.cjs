const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('static/js/components/study/sub_diary_generate.js','utf8');
function setup(mode){const notices=[],editor={value:'합성 일기'},button={disabled:false};let calls=0,release;
 const pending=new Promise(r=>release=r);
 const ctx=vm.createContext({window:{popupManager:{show:m=>notices.push(m)}},document:{getElementById:id=>id==='diary-editor'?editor:button,addEventListener(){},querySelectorAll:()=>[]},console:{log(){},error(){}},localStorage:{getItem:()=> 'synthetic'},alert:m=>notices.push(m),fetch:async()=>{calls++;if(mode==='pending')await pending;if(mode==='network')throw Error('network');return {ok:mode==='ok'||mode==='pending',json:async()=>({detail:mode==='invalid'?[{msg:'bad'}]:'오늘 이미 직접 작성한 일기가 있습니다.'})}}});
 vm.runInContext(source,ctx);vm.runInContext('loadDiaryList = () => {}',ctx);return {ctx,editor,button,notices,calls:()=>calls,release};}
(async()=>{for(const mode of ['ok','duplicate','invalid','network']){const t=setup(mode);await t.ctx.saveManualDiary();assert.equal(t.calls(),1);assert.equal(t.button.disabled,false);assert.equal(t.editor.value,mode==='ok'?'':'합성 일기');if(mode==='invalid')assert.match(t.notices[0],/50,000/)}
 const t=setup('pending');let first=t.ctx.saveManualDiary();await t.ctx.saveManualDiary();assert.equal(t.calls(),1);assert.equal(t.button.disabled,true);t.release();await first;assert.equal(t.button.disabled,false);
 const long=setup('ok');long.editor.value='a'.repeat(50001);await long.ctx.saveManualDiary();assert.equal(long.calls(),0);
 console.log('PASS manual diary frontend: 6 success/failure/duplicate-submit/length paths');
})().catch(e=>{console.error(e);process.exitCode=1});
