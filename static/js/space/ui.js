export class ApiError extends Error {constructor(message,status=0){super(message);this.status=status;}}
export const $ = id => document.getElementById(id);
export const token = () => localStorage.getItem('access_token');
export const owner = () => localStorage.getItem('user_id');
export function node(tag,className,text){const el=document.createElement(tag);if(className)el.className=className;if(text!==undefined)el.textContent=text;return el;}
export function closeButton(dialog,label='닫기'){const button=node('button','dialog-close','×');button.type='button';button.setAttribute('aria-label',label);button.addEventListener('click',()=>dialog.close());return button;}
export function id(){return crypto.randomUUID();}
export function safeNext(value,fallback='/space'){try{const url=new URL(value,location.origin);return url.origin===location.origin&&/^\/(space|library|passes|diary\/[1-9]\d*)$/.test(url.pathname)?url.pathname+url.search:fallback;}catch{return fallback;}}
export function clearIdentity(){
 const uid=owner();for(const key of ['access_token','nickname','user_id'])localStorage.removeItem(key);
 for(let i=sessionStorage.length-1;i>=0;i--){const key=sessionStorage.key(i);if(key.startsWith(`space:${uid}:`))sessionStorage.removeItem(key);}
 window.dispatchEvent(new Event('space:identity-cleared'));
}
let dialogQueue=Promise.resolve();
function ensureDialog(){
 let el=$('ui-dialog');if(el)return el;
 // 이전 가입 페이지에는 공유 마크업이 없다. 새 JS와 조합돼도 알림을 제공한다.
 el=node('dialog','ui-dialog');el.id='ui-dialog';el.setAttribute('aria-labelledby','dialog-title');el.setAttribute('aria-describedby','dialog-description');
 const form=node('form');form.method='dialog';const close=node('button','dialog-close','×');close.value='cancel';close.type='submit';close.setAttribute('aria-label','알림 닫기');
 const title=node('h2'),description=node('p'),choices=node('div','dialog-choices');title.id='dialog-title';description.id='dialog-description';choices.id='dialog-choices';
 form.append(close,node('div','dialog-emblem','✦'),title,description,choices);el.append(form);document.body.append(el);return el;
}
export function dialog(title,description,choices=[{label:'확인',value:'ok',primary:true}],{dismissible=true,onShown}={}){
 const result=dialogQueue.then(()=>new Promise(resolve=>{
  const el=ensureDialog();$('dialog-title').textContent=title;$('dialog-description').textContent=description;$('dialog-choices').replaceChildren();
  $('dialog-description').hidden=!description;
  const close=el.querySelector('.dialog-close');if(close)close.hidden=!dismissible;
  el.setAttribute('closedby',dismissible?'closerequest':'none');
  const preventCancel=event=>{if(!dismissible)event.preventDefault();};el.addEventListener('cancel',preventCancel);
  const preventEscape=event=>{if(!dismissible&&event.key==='Escape')event.preventDefault();};el.addEventListener('keydown',preventEscape);
  for(const choice of choices){if(choice.label==='닫기')continue;const button=node('button',choice.primary?'primary':'secondary',choice.label);button.value=choice.value;button.type='submit';$('dialog-choices').append(button);}
  el.returnValue='';el.addEventListener('close',()=>{el.removeEventListener('cancel',preventCancel);el.removeEventListener('keydown',preventEscape);resolve(el.returnValue||'cancel');},{once:true});el.showModal();onShown?.();
 }));dialogQueue=result.catch(()=>{});return result;
}
export const confirm = (title,description,yes='확인',no='취소') => dialog(title,description,[{label:no,value:'cancel'},{label:yes,value:'ok',primary:true}]);
let toastTimer;
export function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4000);}
let expired=false;
export async function expire(){if(expired)return;expired=true;const next=safeNext(location.pathname+location.search);clearIdentity();await dialog('다시 로그인해 주세요','로그인이 만료되었거나 유효하지 않습니다.');location.replace('/login?next='+encodeURIComponent(next));}
export async function request(path,{method='GET',data,body,signal,accept,authRedirect=true}={}){
 const sentToken=token();let response;
 try{response=await fetch(path,{method,cache:'no-store',headers:{...(sentToken?{Authorization:`Bearer ${sentToken}`} : {}),...(data?{'Content-Type':'application/json'}:{}),...(accept?{Accept:accept}:{})},body:data?JSON.stringify(data):body,signal});}
 catch(error){if(error.name==='AbortError')throw error;throw new ApiError('연결하지 못했어요. 입력은 그대로 두고 다시 시도해 주세요.');}
 if(sentToken!==token())throw new ApiError('계정이 변경되었습니다.',401);
 if(response.status===401){if(authRedirect)void expire();throw new ApiError('다시 로그인해 주세요.',401);}
 if(!response.ok){let data;try{data=await response.json();}catch{}throw new ApiError(typeof data?.detail==='string'?data.detail:'처리를 완료하지 못했어요. 잠시 후 다시 시도해 주세요.',response.status);}
 return response;
}
export async function json(path,options){return (await request(path,options)).json();}
export async function logout(){try{await fetch('/logout',{method:'POST',headers:{Authorization:`Bearer ${token()}`},signal:AbortSignal.timeout(5000)});}catch{}finally{clearIdentity();location.assign('/');}}
window.addEventListener('storage',event=>{if(['access_token','user_id'].includes(event.key)||event.key===null){window.dispatchEvent(new Event('space:identity-cleared'));location.replace('/login?next=%2Fspace');}});

// token 단위가 아닌 완성 말풍선 SSE 계약. 저장 이벤트 없이 EOF면 실패다.
export async function readSSE(response,onBubble,valid=()=>true){
 if(!response.headers.get('content-type')?.includes('text/event-stream'))throw new ApiError('화면을 새로고침한 뒤 다시 시도해 주세요.');
 const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',saved=false,index=0;
 function frame(raw){let event='',parts=[];for(const line of raw.split('\n')){if(line.startsWith('event:'))event=line.slice(6).trim();if(line.startsWith('data:'))parts.push(line.slice(5).trimStart());}if(!parts.length)return;
  const data=JSON.parse(parts.join('\n'));if(!valid())throw new ApiError('계정 또는 작성이 변경되었습니다.',401);
  if(event==='error')throw new ApiError(data.message||'답변을 저장하지 못했어요. 다시 시도해 주세요.');
  if(event==='bubble'){if(!Number.isInteger(data.index)||typeof data.text!=='string')throw new ApiError('답변 형식을 확인하지 못했어요.');if(data.index<index)return;if(data.index!==index)throw new ApiError('답변 순서가 올바르지 않아요.');onBubble(data.text,index++);}
  if(event==='saved')saved=true;
 }
 try{while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});buffer=buffer.replace(/\r\n/g,'\n');let split;while((split=buffer.indexOf('\n\n'))>=0){frame(buffer.slice(0,split));buffer=buffer.slice(split+2);}if(buffer.length>250000)throw new ApiError('답변 형식을 확인하지 못했어요.');if(done)break;}if(buffer.trim())frame(buffer);if(!saved)throw new ApiError('답변 연결이 끊겼어요. 같은 요청으로 다시 시도해 주세요.');}
 finally{await reader.cancel().catch(()=>{});}
}
