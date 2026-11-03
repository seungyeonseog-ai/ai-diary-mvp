import {$,json,node,token,owner,confirm,expire} from './ui.js?v=20261103-7c';
const identity=token(),uid=owner(),same=()=>identity===token()&&uid===owner();
let sequence=0,view='today',lastSignature=null,retry=null,polling=false,acting=false;
const root=$('letter-content'),status=$('daily-inbox-status'),error=$('letter-page-error');
function select(next){view=next;$('daily-inbox').textContent=view==='received'?'받은편지':'오늘 받은편지';for(const [id,name]of [['daily-inbox','today'],['daily-archive','archive']]){const selected=name===view||name==='today'&&view==='received';$(id).setAttribute('aria-selected',String(selected));$(id).tabIndex=selected?0:-1;}$('letter-page-panel').setAttribute('aria-labelledby',view!=='archive'?'daily-inbox':'daily-archive');}
function route(next,key){const params=new URLSearchParams();if(next==='archive')params.set('view','archive');if(key)params.set('letter',key);history.replaceState(null,'','/letters'+(params.size?'?'+params:''));}
function begin(next){select(next);const epoch=++sequence;root.replaceChildren();error.hidden=true;error.replaceChildren();status.textContent='편지를 불러오고 있어요.';return epoch;}
function fail(exc,action){if(!same()||exc.status===401)return;status.textContent='';error.hidden=false;const button=node('button','secondary','다시 불러오기');button.addEventListener('click',action);error.replaceChildren(node('p','',exc.message),button);retry=action;}
function locked(data){const section=node('div','empty-detail');const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');icon.setAttribute('class','icon empty-lock');icon.setAttribute('aria-hidden','true');const use=document.createElementNS(icon.namespaceURI,'use');use.setAttribute('href','#i-lock');icon.append(use);
 const title=data.state==='discarded'?'오늘의 편지는 이미 처리했어요.':data.state==='skipped'?'오늘의 편지는 쉬어가요.':'아직 도착한 응원 편지가 없어요.';
 section.append(icon,node('strong','',title),node('p','','오늘의 이야기를 들려주시면 예약 시각에 따뜻한 응원을 전해드려요.'),node('p','',`응원 예약 시간은 ${String(data.hour).padStart(2,'0')}:00예요. (한국 시간)`));root.append(section);}
async function renderToday(prefetched){route('today');const epoch=begin('today');try{const data=prefetched||await json('/daily/inbox');if(!same()||epoch!==sequence)return;
 lastSignature=JSON.stringify([data.server_date,data.state,data.letter?.id,data.letter?.saved,data.letter?.discarded]);status.textContent='';
 if(data.letter)await renderLetter(data.letter.id,'today',epoch);else locked(data);
 }catch(exc){if(epoch===sequence)fail(exc,()=>renderToday());}}
async function renderArchive(){route('archive');const epoch=begin('archive');try{const data=await json('/daily/letters?view=archive');if(!same()||epoch!==sequence)return;status.textContent='';
 if(!data.items.length){const empty=node('div','empty-detail');empty.append(node('strong','','아직 보관한 편지가 없어요.'),node('p','','마음에 남는 응원 편지를 보관해 보세요.'));root.append(empty);}
 for(const item of data.items){const button=node('button','letter-list-item',`${item.date}의 응원 편지`);button.addEventListener('click',()=>open(item.id,'archive'));root.append(button);}
 }catch(exc){if(epoch===sequence)fail(exc,renderArchive);}}
async function open(id,origin='today'){route(origin,id);const epoch=begin(origin);await renderLetter(id,origin,epoch);}
async function renderLetter(id,origin,epoch){try{const data=await json(`/daily/letters/${id}`);if(!same()||epoch!==sequence)return;
 status.textContent='';root.replaceChildren();const article=node('article','letter-paper'),lamp=node('img','letter-corner-lamp');lamp.src='/static/images/space/lamp-default-v1.png';lamp.alt='따뜻하게 빛나는 전등';
 article.append(lamp,node('p','letter-date',data.date),node('div','letter-body',data.body));const actions=node('div','daily-actions');
 if(data.archive_deleted)actions.append(node('p','','보관함에서 삭제한 편지예요.'));
 else if(!data.saved){for(const [action,label]of [['save','보관함에 저장'],['discard','폐기']]){const button=node('button',action==='save'?'primary':'secondary',label);button.addEventListener('click',()=>act(id,action,origin,epoch,actions));actions.append(button);}}
 else{actions.append(node('p','','보관한 편지예요.'));if(origin==='archive'){const button=node('button','secondary','보관함에서 삭제');button.addEventListener('click',()=>act(id,'archive-delete',origin,epoch,actions));actions.append(button);}}
 article.append(actions);if(origin==='archive'){const back=node('button','text-button','‹ 보관함 목록으로');back.addEventListener('click',renderArchive);article.append(back);}root.append(article);
 void json(`/daily/letters/${id}/view`,{method:'POST'}).catch(exc=>{if(epoch===sequence)fail(exc,()=>open(id,origin));});
 }catch(exc){if(epoch===sequence)fail(exc,()=>open(id,origin));}}
async function act(id,action,origin,epoch,actions){
 if(acting||!same()||epoch!==sequence)return;acting=true;const buttons=[...actions.querySelectorAll('button')];
 try{
  if(action!=='save'&&await confirm(action==='discard'?'편지를 폐기할까요?':'보관함에서 삭제할까요?',action==='discard'?'폐기한 오늘 편지는 다시 받을 수 없어요.':'보관함에서 이 편지를 삭제합니다.')!=='ok')return;
  if(!same()||epoch!==sequence)return;buttons.forEach(b=>b.disabled=true);
  await json(`/daily/letters/${id}/${action}`,{method:'POST'});if(!same()||epoch!==sequence)return;window.dispatchEvent(new Event('daily:changed'));if(origin==='archive')await renderArchive();else if(origin==='received'&&action==='save')await open(id,'received');else await renderToday();
 }catch(exc){if(epoch===sequence)fail(exc,()=>open(id,origin));}
 finally{acting=false;buttons.forEach(b=>b.disabled=false);}
}
$('daily-inbox').addEventListener('click',()=>renderToday());$('daily-archive').addEventListener('click',renderArchive);
for(const id of ['daily-inbox','daily-archive'])$(id).addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?'today':e.key==='End'?'archive':view==='archive'?'today':'archive';(next==='today'?$('daily-inbox'):$('daily-archive')).focus();if(next==='today')void renderToday();else void renderArchive();}});
async function sync(){if(!same()||view!=='today'||polling)return;polling=true;try{const data=await json('/daily/inbox');if(!same()||view!=='today')return;const signature=JSON.stringify([data.server_date,data.state,data.letter?.id,data.letter?.saved,data.letter?.discarded]);if(lastSignature!==null&&signature!==lastSignature)await renderToday(data);}catch{/* foreground load keeps its explicit retry */}finally{polling=false;}}
window.addEventListener('daily:clock',sync);document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')void sync();});
window.addEventListener('pagehide',()=>{sequence++;});
window.addEventListener('space:identity-cleared',()=>{sequence++;root.replaceChildren();status.textContent='';error.replaceChildren();});
if(!token())void expire();else{const params=new URLSearchParams(location.search),key=params.get('letter');if(key&&/^[1-9]\d*$/.test(key))void open(Number(key),params.get('view')==='archive'?'archive':'received');else if(params.get('view')==='archive')void renderArchive();else void renderToday();}
