import {json,node,token,owner,toast,dialog,logout,closeButton} from './ui.js?v=20261104-ui2';
const identity=token(),uid=owner(),same=()=>token()===identity&&owner()===uid;
let stopped=false,timer,lastIds=null,snapshot=0,requesting=false,revision=0;
const panel=node('dialog','ui-dialog daily-panel');panel.setAttribute('aria-label','편지와 알림');document.body.append(panel);
const title=node('h2'),content=node('div','daily-content'),error=node('p','daily-error'),close=closeButton(panel,'알림 닫기');
panel.append(title,content,error,close);
function show(name){revision++;title.textContent=name;content.replaceChildren();error.textContent='';if(!panel.open)panel.showModal();return revision;}
panel.addEventListener('cancel',event=>{if(panel.dataset.required==='true')event.preventDefault();});
panel.addEventListener('keydown',event=>{if(panel.dataset.required==='true'&&event.key==='Escape')event.preventDefault();});
panel.addEventListener('close',()=>{panel.dataset.required='false';panel.setAttribute('closedby','closerequest');close.hidden=false;});
function fail(exc){if(same())error.textContent=exc.message;}
async function settings({waitForClose=false}={}){
 const epoch=show('응원 받을 시간');
 panel.dataset.required=String(waitForClose);panel.setAttribute('closedby',waitForClose?'none':'closerequest');close.hidden=waitForClose;
 try{const data=await json('/daily/settings');if(!same()||epoch!==revision||!panel.open)return;
  const label=node('label','','대화를 시작하면 설정하신 시간대에 응원메세지를 남겨드려요 (한국시간)'),select=node('select');select.setAttribute('aria-label','응원 예약 시간');
  for(let hour=0;hour<24;hour++){const option=node('option','',`${String(hour).padStart(2,'0')}:00`);option.value=hour;select.append(option);}select.value=data.hour;
  const note=node('p','','※ 오늘 편지를 이미 받았다면 변경한 시간은 내일부터 적용돼요.'),save=node('button','primary','완료');
  save.addEventListener('click',async()=>{save.disabled=true;error.textContent='';try{const result=await json('/daily/settings',{method:'PUT',data:{hour:Number(select.value)}});if(!same())return;toast(`응원 시간 ${String(result.hour).padStart(2,'0')}:00 · ${result.effective_date}부터 적용`);panel.close();await refresh();}catch(exc){fail(exc);}finally{save.disabled=false;}});
  label.append(select);content.append(label,note,save);
  if(waitForClose)await new Promise(resolve=>panel.addEventListener('close',resolve,{once:true}));
 }catch(exc){if(!same()||epoch!==revision||!panel.open)return;fail(exc);const retry=node('button','primary','다시 불러오기');retry.addEventListener('click',()=>void settings({waitForClose}));content.append(retry);if(waitForClose)await new Promise(resolve=>panel.addEventListener('close',resolve,{once:true}));}
}
async function list(view='pending'){
 const epoch=show(view==='archive'?'보관한 편지':'알림');
 try{const data=await json(`/daily/letters?view=${view}`);if(!same()||epoch!==revision)return;
  if(!data.items.length)content.append(node('p','',view==='archive'?'아직 보관한 편지가 없어요.':'처리하지 않은 편지가 없어요.'));
  for(const item of data.items){const button=node('button','letter-list-item',`${item.date}의 응원 편지${item.viewed?' · 열어본 편지':''}`);button.addEventListener('click',()=>openLetter(item.id,view));content.append(button);}
  if(view==='pending')content.append(node('p','soft-copy','오늘 받은편지가 비활성화된 뒤에도 놓친 편지는 여기에서 열 수 있어요.'));
 }catch(exc){fail(exc);}
}
async function openLetter(id,origin='today'){panel.close();location.assign(`/letters?letter=${encodeURIComponent(id)}${origin==='archive'?'&view=archive':''}`);}
async function today(){try{const data=await json('/daily/inbox');if(!same())return;if(data.letter)await openLetter(data.letter.id);else toast(data.state==='skipped'?'예약 시각에 대화가 없어 오늘 편지는 쉬어가요.':data.state==='discarded'?'오늘 편지는 이미 처리했어요.':`응원 예약 시간은 ${data.hour}:00예요.`);}catch(exc){toast(exc.message);}}
async function inboxStatus(){
 const button=document.getElementById('daily-inbox');if(!button||document.getElementById('letters-workspace'))return;
 try{const data=await json('/daily/inbox');if(!same())return;button.disabled=!data.letter;
  document.getElementById('daily-inbox-status').textContent=data.letter?'오늘의 편지가 도착했어요.':data.state==='unavailable'?'현재 이용권에는 새 응원 편지가 포함되지 않아요. 기존 편지는 계속 볼 수 있어요.':data.state==='skipped'?'예약 시각에 대화가 없어 오늘 편지는 쉬어가요.':data.state==='discarded'?'오늘 편지는 이미 처리했어요.':`오늘의 응원 예약은 ${String(data.hour).padStart(2,'0')}:00예요.`;
 }catch(exc){button.disabled=true;document.getElementById('daily-inbox-status').textContent=exc.message;}
}
function badge(count){for(const element of document.querySelectorAll('.library-notice-count')){element.hidden=count===0;element.textContent=count;element.setAttribute('aria-label',`새 결과 ${count}개`);}}
async function refresh(){
 if(!identity||!same()||stopped||requesting)return;requesting=true;
 try{const data=await json('/daily/notices');if(!same())return;
  snapshot=data.through_id;badge(data.count);
  const ids=new Set(data.items.map(x=>x.id));
  if(lastIds!==null){const arrivals=data.items.filter(x=>!lastIds.has(x.id)&&!x.seen);if(arrivals.length){const banner=document.getElementById('daily-arrival');banner.hidden=false;banner.textContent=arrivals.some(x=>x.kind==='letter')?'새 응원 편지가 도착했어요. 눌러서 확인해 보세요.':'새 주간 차트가 도착했어요. 서재에서 확인해 보세요.';banner.onclick=()=>{banner.hidden=true;if(arrivals.some(x=>x.kind==='letter'))void list();else location.assign('/weekly');};window.dispatchEvent(new Event('daily:changed'));}}
  const initial=lastIds===null;lastIds=ids;
  if(initial&&location.pathname==='/library'){await json('/daily/notices/seen',{method:'POST',data:{through_id:snapshot}});if(same())badge(0);}
 }catch(exc){if(same()){const status=document.getElementById('daily-sync-status');if(status)status.textContent='알림 연결을 확인 중이에요.';}}
 finally{requesting=false;}
}
function start(){
 if(!identity)return;
 const banner=node('button','daily-arrival');banner.id='daily-arrival';banner.hidden=true;banner.setAttribute('aria-live','polite');document.body.append(banner);
 const notice=document.getElementById('daily-notifications');notice?.addEventListener('click',()=>list());
 if(!document.getElementById('letters-workspace')){document.getElementById('daily-archive')?.addEventListener('click',()=>list('archive'));document.getElementById('daily-inbox')?.addEventListener('click',today);}
 document.getElementById('account')?.addEventListener('click',async event=>{event.stopImmediatePropagation();const choice=await dialog('나의 계정',`${localStorage.getItem('nickname')||'나'}님\n이야기는 로그인한 계정에만 보관돼요.`,[{label:'홈페이지',value:'home'},{label:'로그아웃',value:'logout',primary:true}]);if(choice==='home')location.assign('/');else if(choice==='logout')await logout();},true);
 for(const button of document.querySelectorAll('.coming-soon'))button.addEventListener('click',event=>{event.stopImmediatePropagation();void dialog(`${button.dataset.feature}은 준비 중이에요`,'지금은 홈과 서재에서 당신의 이야기를 남겨보세요.');},true);
 // 기존 설정 버튼의 계정 메뉴와 동시에 열리지 않게 별도 이벤트를 받는다.
 document.getElementById('settings')?.addEventListener('click',event=>{event.stopImmediatePropagation();void settings();},true);
 void refresh();void inboxStatus();timer=setInterval(()=>{void refresh();void inboxStatus();window.dispatchEvent(new Event('daily:clock'));},15000);
 // 첫 안내와 응원 설정은 access_status.js의 한 흐름으로 제공한다.
}
window.addEventListener('daily:socket',()=>void refresh());
window.addEventListener('daily:changed',()=>void inboxStatus());
window.addEventListener('space:identity-cleared',()=>{stopped=true;revision++;clearInterval(timer);panel.close();content.replaceChildren();badge(0);document.getElementById('daily-arrival')?.remove();});
window.addEventListener('pagehide',()=>{stopped=true;clearInterval(timer);});
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')void refresh();});
start();
export {settings,list,openLetter};
