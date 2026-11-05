import {$,node,id,token,owner,json,request,readSSE,dialog,confirm,toast,logout,expire,safeNext} from './ui.js?v=20261104-ui2';
import {replyReadingDelay,PHOTO_LIMIT} from './writing_policy.js?v=20261103-8a';
let state=null,busy=false,editing=false,editingVersion=null,retry=null,poll=null,epoch=0,activeController=null,photoURLs=[],failedPhotos=[];
let diaryPromptTimer=null,photoLimitNotice=false,leaving=false;
function cancelDiaryPrompt(){clearTimeout(diaryPromptTimer);diaryPromptTimer=null;}
function scheduleDiaryPrompt(text){
 if(diaryPromptTimer!==null)return;
 const writingId=state?.id,reply=latestReply();
 if(reply&&stored('diary-prompt')===reply.request_id)return;
 diaryPromptTimer=setTimeout(()=>{diaryPromptTimer=null;
  if(same()&&state?.id===writingId&&(!reply||latestReply()?.request_id===reply.request_id)&&!state.diary&&!busy&&!editing&&document.visibilityState==='visible'&&!$('message-input').value.trim()&&unsubmitted().length===0)void askDiary();
 },replyReadingDelay(text));
}
function openCompletedDiary(){cancelDiaryPrompt();leaving=true;location.assign(`/diary/${state.diary.id}?return=${encodeURIComponent(backURL)}`);}
function goToLibrary(highlight=false){
 if(highlight)try{sessionStorage.setItem(`space:${uid}:saved-book`,String(state.diary.id));}catch{}
 leaving=true;location.assign('/library');
}
const detailId=$('workspace').dataset.diaryId||null;
const requestedBack=safeNext(new URLSearchParams(location.search).get('return')||'/library','/library');
const backURL=requestedBack.split('?')[0]==='/library'?requestedBack:'/library';
if($('diary-back'))$('diary-back').href=backURL;
const identity=token(),uid=owner();
const same=()=>token()===identity&&owner()===uid;
const key=name=>`space:${uid}:${state?.id||'today'}:${name}`;
const composerResumeKey=`space:${uid}:composer-resume`;
const store=(name,value)=>{try{if(value===null)sessionStorage.removeItem(key(name));else sessionStorage.setItem(key(name),JSON.stringify(value));
 if(name==='composer'&&!detailId){if(value===null)sessionStorage.removeItem(composerResumeKey);else sessionStorage.setItem(composerResumeKey,JSON.stringify({id:state.id,date:state.date,text:value}));}
 }catch{/* 저장 공간이 없어도 서버 저장 흐름은 유지 */}};
const stored=name=>{try{return JSON.parse(sessionStorage.getItem(key(name)));}catch{return null;}};
function clearLocal(){for(let i=sessionStorage.length-1;i>=0;i--){const k=sessionStorage.key(i);if(k.startsWith(`space:${uid}:${state.id}:`))sessionStorage.removeItem(k);}try{sessionStorage.removeItem(composerResumeKey);}catch{}}
async function restoreDayComposer(){
 if(detailId)return;
 const current=stored('composer');if(typeof current==='string'){store('composer',current);return;}
 const writingId=state.id;let previous=null;
 try{previous=JSON.parse(sessionStorage.getItem(composerResumeKey));}catch{}
 if(previous&&typeof previous.text==='string'&&previous.date<state.date){store('composer',previous.text);
  if(stored('composer')===previous.text&&typeof previous.id==='string'&&/^[A-Za-z0-9-]{1,80}$/.test(previous.id)&&previous.id!==state.id)try{sessionStorage.removeItem(`space:${uid}:${previous.id}:composer`);}catch{}
  return;}
 // 구형 열린 화면은 날짜별 작성 키만 사용했다. 본인 작성의 날짜를 서버에서 확인한다.
 if(previous)return;
 const prefix=`space:${uid}:`,suffix=':composer';let best=null,keys=[];
 try{for(let i=0;i<sessionStorage.length;i++)keys.push(sessionStorage.key(i));}catch{return;}
 for(const candidate of keys){
  if(!candidate.startsWith(prefix)||!candidate.endsWith(suffix))continue;
  const sourceId=candidate.slice(prefix.length,-suffix.length);if(sourceId===writingId||!/^[A-Za-z0-9-]{1,80}$/.test(sourceId))continue;
  let text;try{text=JSON.parse(sessionStorage.getItem(candidate));}catch{continue;}if(typeof text!=='string'||!text)continue;
  try{const old=await json(`/writing/${encodeURIComponent(sourceId)}`);if(!same()||state.id!==writingId)return;
   if(old.state==='active'&&old.date<state.date&&(!best||old.date>best.date))best={date:old.date,text,key:candidate};
  }catch{/* 조회 불가·타계정·폐기된 작성은 복원하지 않는다. */}
 }
 if(best&&same()&&state.id===writingId){store('composer',best.text);if(stored('composer')===best.text)try{sessionStorage.removeItem(best.key);}catch{}}
}
function show(view){for(const name of ['loading','chat','generating','diary'])$(name+'-view').hidden=name!==view;$('workspace').dataset.view=view;}
function error(message,action,label='다시 시도',kind=''){if(!same())return;$('error-message').textContent=message;$('error-panel').dataset.kind=kind;$('error-panel').hidden=false;retry=action;$('retry-action').hidden=!action;$('retry-action').textContent=label;}
function clearError(){$('error-panel').hidden=true;retry=null;}
function setBusy(value){busy=value;$('workspace').setAttribute('aria-busy',String(value));updateActions();}
function ops(){return state?.operations||[];}
function unsubmitted(){const submitted=new Set(ops().filter(o=>o.kind==='lamp').flatMap(o=>o.source_ids||[]));return(state?.messages||[]).filter(m=>m.role==='user'&&!submitted.has(m.id));}
function latestReply(){return ops().findLast(op=>op.kind==='lamp'&&op.state==='succeeded');}
function success(){return Boolean(latestReply());}
function updateActions(){
 const allowance=state?.quota,remaining=(allowance?.base_remaining||0)+(allowance?.extra_remaining||0);
 const unresolved=ops().some(o=>['failed','pending'].includes(o.state));
 for(const name of ['message-input','send-message','lamp-submit','make-diary','edit-diary','add-photo','discard-diary','cancel-edit'])$(name).disabled=busy;
 if(state&&!detailId){$('send-message').disabled=busy||remaining===0||unresolved;$('message-input').disabled=busy||remaining===0||unresolved;
 $('lamp-submit').disabled=busy||unresolved||(remaining>0&&!state.messages.length&&!$('message-input').value.trim());
 $('make-diary').hidden=state.diary?.state!=='draft';
 $('make-diary').textContent='작성 중인 일기 열기';
 $('lamp-submit').dataset.available=String(remaining>0&&!unresolved);
 $('lamp-submit').dataset.spent=String(remaining===0);
 $('lamp-submit').dataset.ready=String(!busy&&!unresolved&&remaining>0&&unsubmitted().length>0);
 $('lamp-submit').setAttribute('aria-label',`전등으로 이야기 보내기 · 기본 ${allowance.base_remaining}회 · 추가 ${allowance.extra_remaining}회 남음`);
 $('quota-label').textContent=`기본 ${allowance.base_remaining}회 · 오늘 추가 ${allowance.extra_remaining}회 남음`;
 if($('quota-display')){
  // 이전에 열린 HTML도 같은 조명 상태 갱신을 사용할 수 있다.
  if($('base-quota-text'))$('base-quota-text').textContent='';
  if($('extra-quota-text'))$('extra-quota-text').textContent='';
  const extraVisible=!allowance.features||allowance.features.includes('dialogue');
  const baseIcon=$('base-quota-icon');
  if(baseIcon&&!baseIcon.hidden)baseIcon.dataset.lit=String(remaining>(extraVisible?2:0));
  for(let index=1;index<=2;index++){
   const icon=$('extra-quota-icon-'+index);
   icon.hidden=!extraVisible;
   icon.dataset.lit=String((baseIcon&&!baseIcon.hidden?remaining:allowance.extra_remaining)>2-index);
  }
  if($('quota-tooltip'))$('quota-tooltip').textContent=remaining>0?`오늘 답변을 ${remaining}번 더 받을 수 있어요. 답변을 받을 때마다 전등이 하나씩 꺼져요.`:'오늘 받을 수 있는 답변을 모두 사용했어요.';
 }
 if(remaining===0&&!state.diary&&!unresolved)$('reply-status').textContent='오늘의 대화를 마쳤어요. 이 이야기로 일기를 남겨보세요.';
 }
 $('save-diary').disabled=busy||editing||state?.diary?.state==='saved';
 const completed=state?.diary?.state==='saved'&&!editing;
 $('add-photo').disabled=busy;$('add-photo').hidden=completed;
 $('edit-diary').disabled=busy;$('edit-diary').hidden=editing;
 $('discard-diary').hidden=editing;$('save-diary').hidden=editing||completed;
 $('edit-actions').hidden=!editing;$('apply-edit').disabled=busy;
 $('save-note').hidden=editing||completed;
 $('workspace').dataset.editing=String(editing);
 for(const button of $('photos').querySelectorAll('button'))button.disabled=busy;
 for(const button of $('photo-errors').querySelectorAll('button'))button.disabled=busy;
}
function bubble(text,role,provisional=false){const el=node('div',`bubble ${role}${provisional?' provisional':''}`,text);$('messages').append(el);$('messages').scrollTop=$('messages').scrollHeight;return el;}
function renderChat(){
 show('chat');
 $('messages').replaceChildren();for(const message of state.messages)bubble(message.message,message.role==='user'?'user':'ai');
 $('message-input').value=stored('composer')||'';resizeInput();$('reply-status').textContent='';updateActions();
 $('messages').scrollTop=$('messages').scrollHeight;
}
function resizeInput(){const input=$('message-input');input.style.height='auto';input.style.height=Math.min(input.scrollHeight,140)+'px';}
async function fetchState(){if(detailId){const result=await json(`/writing/diaries/${detailId}`);if(same())state.diary=result;return;}const result=await json(`/writing/${state.id}`);if(!same())return;state=result;}
async function boot(){
 clearTimeout(poll);clearError();setBusy(true);show('loading');
 try{if(detailId){state={id:`diary-${detailId}`,diary:{id:detailId},operations:[],messages:[]};await loadDiary();return;}const result=await json('/writing',{method:'POST'});if(!same())return;state=await json(`/writing/${result.id}`);if(!same())return;await restoreDayComposer();await restore(true);if(sessionStorage.getItem(`space:${uid}:discard-notice`)){sessionStorage.removeItem(`space:${uid}:discard-notice`);await dialog('새 이야기를 시작할 수 있어요','일기와 오늘 대화가 화면에서 사라졌어요. 기본 대화 1회는 다시 사용할 수 있고, 오늘 사용한 추가 횟수는 그대로예요.');}}
 catch(failure){if(failure.status!==401){if(detailId){show('loading');$('loading-view').querySelector('.soft-spinner').hidden=true;$('loading-view').querySelector('p').textContent='일기를 열지 못했어요.';error(failure.message,failure.status===404?()=>location.assign(backURL):boot,failure.status===404?'서재로 돌아가기':'일기 다시 열기');}else{show('chat');error(failure.message,boot,'공간 다시 열기');}}}
 finally{if(!poll)setBusy(false);}
}
async function restore(home=false){
 clearTimeout(poll);poll=null;
 if(!same())return;
 if(!detailId&&state.state==='discarded'){await boot();return;}
 if(state.diary&&(detailId||(!home&&$('workspace').dataset.view==='diary'))){await loadDiary();return;}
 renderChat();
 const unfinished=ops().find(o=>['pending','failed'].includes(o.state));
 if(unfinished){
  const pending=unfinished.state==='pending'&&Date.parse(unfinished.retry_after+'+09:00')>Date.parse(state.server_now);
  if(pending){if(unfinished.kind==='diary')show('generating');else $('reply-status').textContent='이야기를 정리하고 있어요…';setBusy(true);poll=setTimeout(async()=>{poll=null;try{await fetchState();setBusy(false);await restore();}catch(failure){setBusy(false);error(failure.message,refresh,'상태 다시 확인');}},2000);}
 else error(unfinished.kind==='diary'?'일기를 완성하지 못했어요. 이야기는 보관되어 있어요.':'답변을 완성하지 못했어요. 이야기는 보관되어 있어요.',()=>unfinished.kind==='diary'?generateDiary(unfinished.request_id):sendLamp(unfinished.request_id),'다시 시도',unfinished.kind==='lamp'?'reply':'');
 }else if(success()&&unsubmitted().length===0){
  $('reply-status').textContent=state.diary?'오늘 나눈 이야기예요.':'이 이야기로 일기를 남길 수 있어요.';
  if(!state.diary&&!$('message-input').value.trim())scheduleDiaryPrompt(state.messages.filter(m=>m.role!=='user').slice(-3).map(m=>m.message).join(' '));
 }
 updateActions();
 const scrollToLatest=()=>{if(same()&&$('workspace').dataset.view==='chat')$('messages').scrollTop=$('messages').scrollHeight;};
 scrollToLatest();window.requestAnimationFrame?.(scrollToLatest);
}
async function refresh(){clearError();setBusy(true);try{await fetchState();await restore();}catch(failure){if(detailId&&failure.status===404){revokePhotos();$('diary-title').textContent='';$('diary-body').textContent='';$('photos').replaceChildren();show('loading');$('loading-view').querySelector('.soft-spinner').hidden=true;$('loading-view').querySelector('p').textContent='이 일기는 더 이상 열 수 없어요.';error(failure.message,()=>location.assign(backURL),'서재로 돌아가기');}else error(failure.message,refresh,'상태 다시 확인');}finally{if(!poll)setBusy(false);}}

async function ensureToday(){
 await fetchState();
 if(state.date===state.server_now.slice(0,10))return true;
 const input=$('message-input').value;
 const today=await json('/writing',{method:'POST'}),next=await json(`/writing/${today.id}`);if(!same())return false;clearLocal();state=next;
 if(input)store('composer',input);renderChat();toast('새로운 하루가 시작됐어요. 오늘의 이야기를 남겨주세요.');return false;
}

async function sendMessage(){
 const text=$('message-input').value.trim();if(!text)return true;
 await ensureToday();
 let pending=stored('message-request');if(!pending||pending.message!==text)pending={request_id:id(),message:text};store('message-request',pending);
 try{await json(`/writing/${state.id}/messages`,{method:'POST',data:pending});if(!same())return false;
  store('message-request',null);store('composer',null);$('message-input').value='';resizeInput();await fetchState();renderChat();return true;
 }catch(failure){if(failure.status!==401)error(failure.message,submitMessage,'이야기 다시 남기기');return false;}
}
async function submitMessage(event){event?.preventDefault();if(busy||!state)return;clearError();setBusy(true);try{await sendMessage();}finally{setBusy(false);$('message-input').focus();}}

async function askDiary(){
 cancelDiaryPrompt();
 if(busy||!same())return;
 const reply=latestReply();if(reply)store('diary-prompt',reply.request_id);
 updateActions();
 const answer=await confirm('이 이야기로 일기를 만들까요?','오늘 나눈 이야기를 당신의 말로 차근차근 정리할게요.','일기 만들기','더 이야기할래요');
 if(answer==='ok')await generateDiary();else $('message-input').focus();
}
async function sendLamp(requestId){
 cancelDiaryPrompt();
 if(busy||!state)return;clearError();setBusy(true);const generationEpoch=++epoch;activeController=new AbortController();
 try{
  if(!requestId&&!(await sendMessage()))return;
  if(!requestId&&!(await ensureToday()))return;
  if(!requestId&&!unsubmitted().length){setBusy(false);if(state.diary){toast('이야기를 입력한 뒤 전등을 눌러주세요.');$('message-input').focus();}else if(success())await askDiary();return;}
  const operation=requestId||id();store('lamp-request',operation);$('reply-status').textContent='당신의 이야기를 듣고 있어요…';
  const response=await request(`/writing/${state.id}/response_stream`,{method:'POST',data:{request_id:operation},accept:'text/event-stream',signal:activeController.signal});
  await readSSE(response,text=>bubble(text,'ai',true),()=>same()&&generationEpoch===epoch);
  if(!same()||generationEpoch!==epoch)return;
  store('lamp-request',null);await fetchState();renderChat();setBusy(false);
  if(!state.diary)scheduleDiaryPrompt(state.messages.filter(m=>m.role!=='user').slice(-3).map(m=>m.message).join(' '));
 }catch(failure){for(const el of $('messages').querySelectorAll('.provisional'))el.remove();
  if(failure.name!=='AbortError'&&failure.status!==401){$('reply-status').textContent='';const operation=requestId||stored('lamp-request');try{await fetchState();}catch{}error(failure.message,()=>sendLamp(operation),'다시 시도','reply');}
 }finally{activeController=null;setBusy(false);}
}
async function generateDiary(requestId){
 if(busy||!state)return;clearError();setBusy(true);show('generating');
 const operation=requestId||stored('diary-request')||id();store('diary-request',operation);
 try{if(!(await ensureToday()))return;show('generating');await json(`/writing/${state.id}/generate/diary`,{method:'POST',data:{request_id:operation}});if(!same())return;store('diary-request',null);await fetchState();await loadDiary();}
 catch(failure){if(failure.status!==401){try{await fetchState();}catch{}renderChat();error(failure.message,()=>generateDiary(operation),'일기 생성 다시 시도');}}
 finally{setBusy(false);}
}

function revokePhotos(){for(const url of photoURLs)URL.revokeObjectURL(url);photoURLs=[];}
async function loadDiary(){
 const diaryId=state.diary.id;const detail=await json(`/writing/diaries/${diaryId}`);if(!same())return;state.diary=detail;
 editing=false;$('edit-form').hidden=true;$('diary-title').hidden=false;$('diary-body').hidden=false;
 $('diary-title').textContent=detail.title||'오늘의 기록';$('diary-body').textContent=detail.body;
 $('diary-date').textContent=new Intl.DateTimeFormat('ko-KR',{year:'numeric',month:'long',day:'numeric',weekday:'long',timeZone:'Asia/Seoul'}).format(new Date(detail.date+'T12:00:00+09:00'));
 $('diary-state').textContent=detail.state==='saved'?'보관중':'초안';$('save-diary').textContent=detail.state==='saved'?'저장됨':'저장';
 $('save-note').textContent=detail.state==='saved'?'서재에도 보관되었어요.':'저장을 누르면 서재에 보관돼요.';
 if(detail.photos.length<PHOTO_LIMIT)photoLimitNotice=false;renderPhotoErrors();
 show('diary');updateActions();await renderPhotos(detail);if(stored(`edit-${detail.id}`))beginEdit({restore:true});
}
async function renderPhotos(detail){
 revokePhotos();$('photos').replaceChildren();const renderEpoch=++epoch;
 for(let index=0;index<(detail.photos||[]).length;index++){
  const photo=detail.photos[index],figure=node('figure','photo-card');const image=node('img');image.alt=`첨부 사진 ${index+1}`;
  const remove=node('button','', '×');remove.setAttribute('aria-label',`첨부 사진 ${index+1} 삭제`);remove.addEventListener('click',()=>removePhoto(photo.id));remove.disabled=busy;remove.hidden=detail.state==='saved'&&!editing;figure.append(image,remove);$('photos').append(figure);
  try{const response=await request(photo.url);const url=URL.createObjectURL(await response.blob());if(!same()||epoch!==renderEpoch){URL.revokeObjectURL(url);return;}photoURLs.push(url);image.src=url;}
  catch(failure){if(same()&&failure.status!==401){figure.append(node('figcaption','','사진을 불러오지 못했어요.'));error(failure.message,()=>loadDiary(),'사진 다시 불러오기');}}
 }
}
function beginEdit({restore=false}={}){if(busy&&!restore)return;clearError();editing=true;const draft=stored(`edit-${state.diary.id}`);$('edit-title').value=draft?.title??state.diary.title;$('edit-body').value=draft?.body??state.diary.body;
 editingVersion=draft?(draft.version||0):state.diary.version;
 $('edit-form').hidden=false;$('diary-title').hidden=true;$('diary-body').hidden=true;updateActions();for(const button of $('photos').querySelectorAll('button'))button.hidden=false;$('edit-title').focus();}
function rememberEdit(){store(`edit-${state.diary.id}`,{title:$('edit-title').value,body:$('edit-body').value,version:editingVersion});}
async function applyEdit(event){event?.preventDefault();if(busy)return;const title=$('edit-title').value.trim(),body=$('edit-body').value.trim();if(!title||!body){await dialog('제목과 본문을 입력해 주세요','당신의 이야기가 담길 수 있도록 내용을 남겨주세요.');return;}
 if(!editingVersion){await resolveEditConflict();return;}rememberEdit();clearError();setBusy(true);
 try{const result=await json(`/writing/diaries/${state.diary.id}`,{method:'PATCH',data:{version:editingVersion,title,body}});if(!same())return;store(`edit-${state.diary.id}`,null);await loadDiary();if(result.state==='draft'){setBusy(false);await saveDiary();}else goToLibrary();}
 catch(failure){if(failure.status!==401)error(failure.message,failure.status===409?resolveEditConflict:applyEdit,failure.status===409?'최신 내용 확인':'수정 저장 다시 시도');}
 finally{setBusy(false);}
}
async function resolveEditConflict(){
 const fresh=await json(`/writing/diaries/${state.diary.id}`);
 if(fresh.title===$('edit-title').value.trim()&&fresh.body===$('edit-body').value.trim()){store(`edit-${state.diary.id}`,null);clearError();await loadDiary();toast('수정 내용이 이미 반영되어 있어요.');return;}
 const answer=await confirm('일기가 다른 곳에서 바뀌었어요','최신 내용을 열면 현재 입력한 수정 대신 저장된 내용을 보여드려요.','최신 내용 열기','수정 계속하기');
 if(answer==='ok'){store(`edit-${state.diary.id}`,null);clearError();await loadDiary();}else{state.diary.version=fresh.version;editingVersion=fresh.version;rememberEdit();error('수정 내용을 유지했어요. 저장하면 최신 일기에 이 내용을 반영해요.',applyEdit,'이 수정 내용으로 저장');}
}
async function saveDiary(){if(busy||editing)return;clearError();setBusy(true);try{state.diary=await json(`/writing/diaries/${state.diary.id}/save`,{method:'POST',data:{version:state.diary.version}});if(!same())return;goToLibrary(true);}catch(failure){if(failure.status!==401)error(failure.message,saveDiary,'저장 다시 시도');}finally{setBusy(false);}}
async function discardDiary(){if(busy)return;let latest;try{latest=await json(`/writing/diaries/${state.diary.id}`);}catch(failure){error(failure.message,discardDiary);return;}const today=latest.date===latest.server_date;const answer=await confirm('이 일기를 폐기할까요?',today?'폐기한 일기는 서재에서 사라져요. 오늘은 새 이야기로 다시 작성할 수 있어요.':'폐기한 일기는 서재에서 사라져요. 과거 날짜의 일기는 다시 작성할 수 없어요.','폐기하기','계속 간직하기');if(answer!=='ok')return;clearError();setBusy(true);
 try{const result=await json(`/writing/diaries/${state.diary.id}`,{method:'DELETE'});if(!same())return;clearLocal();if(result.can_rewrite_today)try{sessionStorage.setItem(`space:${uid}:discard-notice`,'1');}catch{}leaving=true;location.assign('/space');}
 catch(failure){if(failure.status!==401)error(failure.message,discardDiary,'폐기 다시 시도');}finally{setBusy(false);}}

function renderPhotoErrors(){
 $('photo-errors').replaceChildren();if(photoLimitNotice)$('photo-errors').append(node('div','photo-error','사진은 최대 3장까지 첨부할 수 있어요.'));
 for(const failed of failedPhotos){const row=node('div','photo-error');row.append(node('span','',`${failed.file.name}: ${failed.message}`));const button=node('button','','사진 다시 올리기');button.disabled=busy;button.addEventListener('click',()=>uploadPhotos([failed]));const dismiss=node('button','','선택 해제');dismiss.addEventListener('click',()=>{failedPhotos=failedPhotos.filter(f=>f.id!==failed.id);renderPhotoErrors();});row.append(button,dismiss);$('photo-errors').append(row);}
}
async function reloadPhotosAfterWrite(writtenVersion){
 const keepEditing=editing,oldVersion=state.diary.version,oldTitle=state.diary.title,oldBody=state.diary.body;
 const fresh=await json(`/writing/diaries/${state.diary.id}`);if(!same())return;
 state.diary=fresh;
 if(keepEditing){if(editingVersion===oldVersion&&fresh.version===writtenVersion&&fresh.title===oldTitle&&fresh.body===oldBody){editingVersion=writtenVersion;rememberEdit();}await renderPhotos(fresh);updateActions();}
 else await loadDiary();
 if(fresh.photos.length<PHOTO_LIMIT)photoLimitNotice=false;
 renderPhotoErrors();
}
async function uploadPhotos(entries){if(busy)return;clearError();setBusy(true);for(const entry of entries){
 if(state.diary.photos.length>=PHOTO_LIMIT){photoLimitNotice=true;failedPhotos=failedPhotos.filter(f=>f.id!==entry.id);continue;}
 try{if(entry.file.size>20*1024*1024)throw new Error('장당 20MB까지 첨부할 수 있어요.');
  const result=await json(`/writing/diaries/${state.diary.id}/photos?version=${state.diary.version}&request_id=${entry.id}`,{method:'POST',body:entry.file});if(!same())return;
  failedPhotos=failedPhotos.filter(f=>f.id!==entry.id);await reloadPhotosAfterWrite(result.version);
 }catch(failure){if(failure.status===401){setBusy(false);return;}if(failure.message.includes('최대 3장')){photoLimitNotice=true;failedPhotos=failedPhotos.filter(f=>f.id!==entry.id);}else{entry.message=failure.message;if(!failedPhotos.some(f=>f.id===entry.id))failedPhotos.push(entry);}}
 }setBusy(false);renderPhotoErrors();}
async function removePhoto(photoId){if(busy)return;const answer=await confirm('이 사진을 삭제할까요?','일기 본문과 다른 사진은 그대로 남아 있어요.','사진 삭제','취소');if(answer!=='ok')return;setBusy(true);try{const result=await json(`/writing/diaries/${state.diary.id}/photos/${photoId}`,{method:'DELETE',data:{version:state.diary.version}});await reloadPhotosAfterWrite(result.version);}catch(failure){if(failure.status!==401)error(failure.message,()=>removePhoto(photoId),'사진 삭제 다시 시도');}finally{setBusy(false);}}

$('composer').addEventListener('submit',submitMessage);
$('message-input').addEventListener('input',()=>{cancelDiaryPrompt();store('composer',$('message-input').value);resizeInput();updateActions();});
$('message-input').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();void submitMessage();}});
async function requestLampReply(){
 cancelDiaryPrompt();if(busy||!state||!same())return;
 if(!state.diary&&success()&&!$('message-input').value.trim()&&!unsubmitted().length){
  await askDiary();return;
 }
 const remaining=(state.quota?.base_remaining||0)+(state.quota?.extra_remaining||0);
 if(remaining===0){await dialog('오늘 대화를 다 소진하셨어요','');return;}
 if(!$('message-input').value.trim()&&!unsubmitted().length){await sendLamp();return;}
 const writingId=state.id;
 const answer=await dialog('이야기를 다 남기셨나요?',`답변을 받으시면 추가로 답변받을 수 있는 횟수가 ${remaining-1}번 남아요.`,[
  {label:'다 말했어요, 답변받을래요',value:'reply',primary:true},
  {label:'더 말할래요',value:'more'}]);
 if(!same()||state?.id!==writingId||busy)return;
 if(answer==='reply')await sendLamp();else $('message-input').focus();
}
$('lamp-submit').addEventListener('click',requestLampReply);$('make-diary').addEventListener('click',()=>{if(state?.diary?.state==='draft')openCompletedDiary();});
$('edit-diary').addEventListener('click',beginEdit);$('edit-form').addEventListener('submit',applyEdit);$('edit-title').addEventListener('input',rememberEdit);$('edit-body').addEventListener('input',rememberEdit);
function confirmCancelEdit(){return dialog('수정을 취소할까요?','',[{label:'네',value:'ok',primary:true},{label:'아니요',value:'cancel'}]);}
$('cancel-edit').addEventListener('click',async()=>{if(await confirmCancelEdit()==='ok'){store(`edit-${state.diary.id}`,null);clearError();await loadDiary();}});
$('save-diary').addEventListener('click',saveDiary);$('discard-diary').addEventListener('click',discardDiary);
$('add-photo').addEventListener('click',()=>$('photo-input').click());$('photo-input').addEventListener('change',event=>{const files=[...event.target.files].map(file=>({file,id:id()}));event.target.value='';void uploadPhotos(files);});
$('retry-action').addEventListener('click',()=>retry?.());
for(const button of document.querySelectorAll('.coming-soon'))button.addEventListener('click',()=>dialog(`${button.dataset.feature}은 준비 중이에요`,'지금은 홈과 서재에서 당신의 이야기를 남겨보세요.'));
async function allowLeave(){
 cancelDiaryPrompt();
 if(busy){await dialog('처리 중이에요','저장 중인 내용을 보호하기 위해 처리가 끝난 뒤 이동할 수 있어요.');return false;}
 if(editing||state?.diary?.state==='draft'){
  const draft=state.diary.state==='draft';
  if(!draft){
   if(await confirmCancelEdit()!=='ok'||!same())return false;
   store(`edit-${state.diary.id}`,null);await loadDiary();return true;
  }
  const answer=await dialog('이 일기를 저장하시겠어요?','폐기하면 이 초안과 이번 작성의 대화가 화면에서 사라져요.',
   [{label:'저장하기',value:'save',primary:true},{label:'폐기하기',value:'discard'}]);
  if(answer==='discard'&&same()&&!busy){
   clearError();setBusy(true);
   try{
    await json(`/writing/diaries/${state.diary.id}`,{method:'DELETE'});
    if(!same())return false;
    clearLocal();editing=false;state.diary.state='discarded';leaving=true;location.assign('/space');return false;
   }catch(failure){if(same()&&failure.status!==401)error(failure.message);return false;}
   finally{setBusy(false);}
  }
  if(answer!=='save'||!same()||busy)return false;
  const title=editing?$('edit-title').value.trim():null,body=editing?$('edit-body').value.trim():null;
  if(editing&&(!title||!body)){await dialog('제목과 본문을 입력해 주세요','내용을 채운 뒤 다시 저장해 주세요.');return false;}
  if(editing&&!editingVersion){await resolveEditConflict();return false;}
  clearError();setBusy(true);
  try{
   if(editing){
    rememberEdit();
    const result=await json(`/writing/diaries/${state.diary.id}`,{method:'PATCH',data:{version:editingVersion,title,body}});
    if(!same())return false;
    state.diary=result;editingVersion=result.version;
   }
   if(state.diary.state==='draft'){
    const result=await json(`/writing/diaries/${state.diary.id}/save`,{method:'POST',data:{version:state.diary.version}});
    if(!same())return false;
    state.diary=result;
   }
   store(`edit-${state.diary.id}`,null);editing=false;goToLibrary(true);return false;
  }catch(failure){if(same()&&failure.status!==401)error(failure.message);return false;}
  finally{setBusy(false);}
 }
 return true;
}
async function navigateTo(url){if(await allowLeave()){leaving=true;location.assign(url);}}
async function accountMenu(){if(await dialog('나의 계정',`${localStorage.getItem('nickname')||'나'}님\n이야기는 로그인한 계정에만 보관돼요.`,[{label:'홈페이지',value:'home'},{label:'닫기',value:'cancel'},{label:'로그아웃',value:'logout',primary:true}])==='logout'){if(await allowLeave())await logout();}else if($('ui-dialog').returnValue==='home')await navigateTo('/');}
$('account').addEventListener('click',accountMenu);$('settings').addEventListener('click',accountMenu);
for(const link of document.querySelectorAll('.sidebar a,#diary-back'))link.addEventListener('click',event=>{event.preventDefault();void navigateTo(link.href);});
let resolvingSidebarAction=false;
document.addEventListener('click',async event=>{
 const button=event.target.closest('.sidebar button,#daily-arrival');
 if(!button||(!editing&&state?.diary?.state!=='draft'))return;
 event.preventDefault();event.stopImmediatePropagation();
 if(resolvingSidebarAction)return;
 resolvingSidebarAction=true;
 try{if(await allowLeave())button.click();}
 finally{resolvingSidebarAction=false;}
},true);
window.addEventListener('beforeunload',event=>{
 if(leaving)return;
 const dirty=editing&&($('edit-title').value!==state?.diary?.title||$('edit-body').value!==state?.diary?.body);
 // 수정 문장은 계정/작성별 sessionStorage로 복원한다. 저장공간 장애일 때만 이탈 경고.
 if(busy||dirty||state?.diary?.state==='draft'||failedPhotos.length){event.preventDefault();event.returnValue='';}
});
window.addEventListener('space:identity-cleared',()=>{cancelDiaryPrompt();epoch++;busy=false;editing=false;clearTimeout(poll);activeController?.abort();socket?.close(1000);revokePhotos();$('messages').replaceChildren();$('diary-title').textContent='';$('diary-body').textContent='';$('edit-title').value='';$('edit-body').value='';$('photos').replaceChildren();$('message-input').value='';});
let socket;
function connectNotifications(){
 if(!same()||!token()||!uid)return;
 window.globalNotificationManager=window.createNotificationManager?.();
 socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws/${encodeURIComponent(uid)}`);
 socket.onopen=()=>{if(same())socket.send(JSON.stringify({type:'authenticate',token:identity}));window.studyState?.refresh(true);};
 socket.onmessage=event=>{if(!same())return;try{const data=JSON.parse(event.data);window.dispatchEvent(new Event('daily:socket'));if(['encourage_available','encourage_unavailable','seven_day_report','chart_loading_complete'].includes(data.type))window.globalNotificationManager?.storeNotification(data);}catch{}};
 socket.onclose=event=>{if(![1000,1008].includes(event.code)&&same())setTimeout(connectNotifications,5000);};
}
window.addEventListener('pagehide',()=>{cancelDiaryPrompt();clearTimeout(poll);socket?.close(1000);activeController?.abort();revokePhotos();});
window.addEventListener('daily:clock',async()=>{
 if(detailId||!same()||!state||busy||editing||$('workspace').dataset.view!=='chat')return;
 const count=state.messages.length,writingId=state.id;
 try{const next=await json(`/writing/${writingId}`);if(!same()||busy||editing||state.id!==writingId)return;state=next;
  if(state.state==='discarded'){await boot();return;}
  if(state.date!==state.server_now.slice(0,10)){cancelDiaryPrompt();setBusy(true);try{await ensureToday();}finally{setBusy(false);}return;}
  if(count!==state.messages.length)await restore();else updateActions();
 }catch{/* 기존 입력은 유지하고 다음 연결에서 다시 조회한다. */}
});
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&state&&!busy&&!editing)void refresh();});
if(!token())void expire();else{void boot();connectNotifications();}
