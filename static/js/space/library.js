import {$,node,token,owner,json,request,dialog,confirm,logout,expire} from './ui.js?v=20261103-7c';
import {calendarCells,shiftMonth,validMonth,libraryState,libraryURL,diaryURL,emotionPoints,shelfBooks,coverURL,chartScale} from './library_model.js?v=20261103-7c';
const identity=token(),uid=owner(),same=()=>token()===identity&&owner()===uid;
const cover=coverURL;
let pickerYear=0,state=null,today=null,sequence=0,cardSequence=0,controller=null,retry=null,photoURLs=[],socket=null,reconnect=null;
function lockIcon(){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('class','icon lock-icon');svg.setAttribute('aria-hidden','true');const use=document.createElementNS(svg.namespaceURI,'use');use.setAttribute('href','#i-lock');svg.append(use);return svg;}
function dateLabel(date){return new Intl.DateTimeFormat('ko-KR',{year:'numeric',month:'long',day:'numeric',weekday:'short',timeZone:'Asia/Seoul'}).format(new Date(date+'T12:00:00+09:00'));}
function clearPhotos(){for(const url of photoURLs)URL.revokeObjectURL(url);photoURLs=[];}
function fail(message,action){$('library-error-message').textContent=message;$('library-error').hidden=false;retry=action;}
async function load(next=null,push=false){
 controller?.abort();controller=new AbortController();const signal=controller.signal,requestSequence=++sequence;
 $('library-workspace').setAttribute('aria-busy','true');$('library-error').hidden=true;$('library-loading').hidden=false;$('shelf-view').hidden=true;$('diaries-view').hidden=true;clearPhotos();
 let wanted=next;
 try{
  let initial;
  if(!today){initial=await json('/library-data/shelf',{signal});today=initial.server_date;}
  wanted=wanted||libraryState(location.search,today);
  $('library-hero').hidden=wanted.view!=='shelf';$('library-workspace').classList.toggle('more-workspace',wanted.view!=='shelf');
  const data=wanted.view==='shelf'?(initial&&wanted.page===1?initial:await json(`/library-data/shelf?page=${wanted.page}`,{signal})):await json(`/library-data/month?month=${wanted.month}&page=${wanted.page}`,{signal});
  if(!same()||requestSequence!==sequence)return;
  today=data.server_date;state={...wanted,page:data.page};
  const url=libraryURL(state);if(push)history.pushState(null,'',url);else history.replaceState(null,'',url);
  if(state.view==='shelf'){renderShelf(data);void loadCards();}else renderMonth(data);
 }catch(error){if(error.name!=='AbortError'&&error.status!==401&&same()&&requestSequence===sequence)fail(error.message,()=>load(wanted));}
 finally{if(requestSequence===sequence){$('library-loading').hidden=true;$('library-workspace').setAttribute('aria-busy','false');}}
}
function renderShelf(data){
 $('shelf-view').hidden=false;$('books').replaceChildren();
 shelfBooks(data.books).forEach((book,index)=>{
  if(book.state==='empty'){$('books').append(node('div','book empty','기록이 채워질 자리'));return;}
  const element=node(book.state==='saved'?'a':'button','book '+book.state+(book.state==='saved'&&Number(book.id)%5===4?' dark-cover':''));if(book.state==='saved')element.href=diaryURL(book.id,state);
  const image=node('img');image.src=book.state==='saved'?cover(book.id):'/static/images/space/book-cover-cocoa-v1.png';image.alt='';
  const copy=node('span','book-copy');
  if(book.state==='saved'){copy.append(node('span','book-title',book.title),node('span','book-date',dateLabel(book.date)));element.title=book.title;}
  else{copy.append(lockIcon(),node('span','book-date',dateLabel(book.date)));element.setAttribute('aria-label',`${book.date} 미래의 기록`);element.addEventListener('click',()=>dialog('아직 오지 않은 날이에요','그날의 이야기를 차근차근 채워보세요.'));}
  element.append(image,copy);$('books').append(element);
 });
 $('books-older').disabled=!data.has_older;$('books-newer').disabled=!data.has_newer;
 $('shelf-page').textContent=data.total?`${data.page} / ${data.pages}`:'';$('empty-shelf').hidden=data.total!==0;
 $('diary-more').href=libraryURL({view:'calendar',month:today.slice(0,7),page:1});
}
function renderMonth(data){
 $('diaries-view').hidden=false;$('calendar-tab').setAttribute('aria-pressed',String(state.view==='calendar'));$('list-tab').setAttribute('aria-pressed',String(state.view==='list'));
 $('month-picker-open').textContent=state.month.replace('-','.');$('month-prev').disabled=state.month==='0001-01';$('month-next').disabled=state.month>=today.slice(0,7);
 $('calendar-view').hidden=state.view!=='calendar';$('list-view').hidden=state.view!=='list';$('empty-month').hidden=data.total!==0;
 if(state.view==='calendar')renderCalendar(data);else renderList(data);
}
function renderCalendar(data){
 $('calendar-days').replaceChildren();
 for(const day of calendarCells(state.month)){
  if(!day){$('calendar-days').append(node('div','calendar-cell blank'));continue;}
  const entries=data.days[day]||[],future=day>today,cell=node('button','calendar-cell'+(day===today?' today':'')+(future?' future':''));cell.dataset.date=day;
  cell.setAttribute('aria-label',`${day} ${future?'아직 오지 않은 날':entries.length?`저장 일기 ${entries.length}개`:'저장 일기 없음'}`);
  cell.append(node('span','day-number',Number(day.slice(-2))));
  if(entries.length){const image=node('img','calendar-book');image.src=cover(entries[0].id);image.alt='';cell.append(image);if(entries.length>1)cell.append(node('span','day-count',`${entries.length}개`));}
  else if(future)cell.append(lockIcon());
  cell.addEventListener('click',()=>openDay(day,entries));$('calendar-days').append(cell);
 }
}
async function openDay(day,entries){
 if(day>today){await dialog('아직 오지 않은 날이에요','오늘의 이야기를 먼저 남겨보세요.');return;}
 if(entries.length===1){location.assign(diaryURL(entries[0].id,state));return;}
 if(entries.length>1){const result=await dialog(dateLabel(day),'열어볼 일기를 골라주세요.',[...entries.map(entry=>({label:entry.title,value:String(entry.id),primary:true})),{label:'닫기',value:'cancel'}]);const entry=entries.find(entry=>String(entry.id)===result);if(entry)location.assign(diaryURL(entry.id,state));return;}
 if(day===today){if(await confirm('오늘의 기록을 남겨볼까요?','아직 오늘 저장한 일기가 없어요.','이야기 남기기','닫기')==='ok')location.assign('/space');}
 else await dialog('이날에는 저장한 일기가 없어요','지난 날짜의 일기는 새로 작성할 수 없어요.');
}
function renderList(data){
 $('diary-list').replaceChildren();$('list-page').textContent=`${data.page} / ${data.pages}`;$('list-prev').disabled=!data.has_newer;$('list-next').disabled=!data.has_older;
 const renderSequence=sequence;
 for(const entry of data.items){
  const link=node('a','diary-row');link.href=diaryURL(entry.id,state);const image=node('img','diary-thumb cover');image.src=cover(entry.id);image.alt='';
  const copy=node('div','diary-row-copy');copy.append(node('p','diary-row-date',dateLabel(entry.date)),node('p','diary-row-title',entry.title),node('p','diary-row-excerpt',entry.excerpt));
  link.append(image,copy,node('span','row-arrow','›'));$('diary-list').append(link);
  if(entry.photo_url)void loadThumbnail(entry.photo_url,image,renderSequence);
 }
}
async function loadThumbnail(path,image,renderSequence){try{const response=await request(path);const url=URL.createObjectURL(await response.blob());if(!same()||renderSequence!==sequence){URL.revokeObjectURL(url);return;}photoURLs.push(url);image.src=url;image.classList.remove('cover');}catch{/* 사진 조회 장애에도 일기 제목/본문과 열람 링크는 유지 */}}
function chart(data){
 const points=emotionPoints(data);if(!points.length)throw Error('표시할 감정 차트 자료가 없어요.');
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 440 180');svg.setAttribute('role','img');svg.setAttribute('aria-label','저장된 주간 감정 점수 흐름');
 const add=(tag,attributes)=>{const el=document.createElementNS(ns,tag);for(const [key,value]of Object.entries(attributes))el.setAttribute(key,value);svg.append(el);return el;};
 for(const value of [-1,0,1])add('line',{x1:24,y1:80-value*55,x2:420,y2:80-value*55,stroke:'#d9b58a',opacity:value===0?'.8':'.3'});
 const scale=chartScale(points);const positions=points.map((point,index)=>({x:points.length===1?220:24+index*396/(points.length-1),y:scale.y(point.value)}));
 const line=positions.map(point=>`${point.x},${point.y}`).join(' ');add('polygon',{points:`${positions[0].x},80 ${line} ${positions.at(-1).x},80`,fill:'#e9a777',opacity:'.22'});add('polyline',{points:line,stroke:'#f0844a','stroke-width':2.5,fill:'none'});
 positions.forEach((point,index)=>{add('circle',{cx:point.x,cy:point.y,r:5,fill:'#f28e58',stroke:'#fff7e8','stroke-width':2});const label=add('text',{x:point.x,y:166,'text-anchor':'middle',fill:'#8c6242','font-size':11});label.textContent=points[index].date.slice(5).replace('-','/');});
 $('weekly-preview').replaceChildren(svg);
}
async function loadCards(){
 const requestSequence=++cardSequence;
 try{const data=await json('/study/status');if(!same()||requestSequence!==cardSequence)return;
  const letterState=data.encouragement.state,letterReady=letterState==='ready';$('letter-lock').hidden=letterReady;
  const letterCopy=letterReady?['오늘의 응원 편지가 도착했어요.','봉투를 열어 따뜻한 마음을 확인해보세요.']:letterState==='waiting_time'?['오늘의 편지를 기다리고 있어요.','응원 편지가 도착하면 이곳에서 확인할 수 있어요.']:letterState==='pending'?['응원 편지를 준비하고 있어요.','잠시 후 다시 확인해 주세요.']:letterState==='skipped'?['오늘의 편지는 쉬어가요.','예약 시각에 대화가 없었어요. 다음 예약을 기다려주세요.']:letterState==='discarded'?['오늘의 편지를 처리했어요.','다음 편지는 내일 예약 시각에 도착해요.']:['오늘의 편지를 기다리고 있어요.','예약 시각 전 오늘의 이야기를 들려주세요.'];
  $('letter-status').textContent=letterCopy[0];$('letter-note').textContent=letterCopy[1];
  if(data.weekly.state==='ready'){try{const weekly=await json('/study/weekly/latest');if(same()&&requestSequence===cardSequence)chart(weekly);}catch(error){if(same()&&requestSequence===cardSequence)cardError(error.message);}}
  else{const hint=node('div','weekly-hint');hint.append(node('p','','대화를 시작한 날부터 7일마다 확인해요.'),node('p','','그 기간에 대화한 날짜가 3일 이상이면 만들어져요.'));$('weekly-preview').replaceChildren(lockIcon(),node('strong','','조금만 더 기록해볼까요?'),node('p','','나만의 주간 차트를 확인할 수 있어요.'),hint);}
 }catch(error){if(same()&&requestSequence===cardSequence&&error.status!==401){$('letter-status').textContent='편지 상태를 불러오지 못했어요.';$('letter-note').textContent='잠시 후 다시 확인해 주세요.';cardError(error.message);}}
}
window.addEventListener('daily:changed',()=>{if(state?.view==='shelf')void loadCards();});
window.addEventListener('daily:clock',()=>{if(state?.view==='shelf')void loadCards();});
function cardError(message){const button=node('button','','상태 다시 확인');button.addEventListener('click',loadCards);$('weekly-preview').replaceChildren(node('p','',message),button);}
function moveMonth(delta){const month=shiftMonth(state.month,delta);if(validMonth(month)&&month<=today.slice(0,7))void load({...state,month,page:1},true);}
function picker(){const year=pickerYear,valid=Number.isInteger(year)&&year>=1&&year<=Number(today.slice(0,4));$('picker-year').textContent=`${year}년`;$('year-prev').disabled=!valid||year===1;$('year-next').disabled=!valid||year>=Number(today.slice(0,4));$('picker-months').replaceChildren();
 for(let number=1;number<=12;number++){const month=`${String(year).padStart(4,'0')}-${String(number).padStart(2,'0')}`,button=node('button',month===state.month?'selected':'',`${number}월`);button.disabled=!valid||month>today.slice(0,7);button.addEventListener('click',()=>{$('month-picker').close();void load({...state,month,page:1},true);});$('picker-months').append(button);}
}
$('books-older').addEventListener('click',()=>load({...state,page:state.page+1},true));$('books-newer').addEventListener('click',()=>load({...state,page:state.page-1},true));
$('calendar-tab').addEventListener('click',()=>load({...state,view:'calendar'},true));$('list-tab').addEventListener('click',()=>load({...state,view:'list'},true));
$('month-prev').addEventListener('click',()=>moveMonth(-1));$('month-next').addEventListener('click',()=>moveMonth(1));
$('list-prev').addEventListener('click',()=>load({...state,page:state.page-1},true));$('list-next').addEventListener('click',()=>load({...state,page:state.page+1},true));
$('month-picker-open').addEventListener('click',()=>{pickerYear=Number(state.month.slice(0,4));picker();$('month-picker').show();$('month-picker-open').setAttribute('aria-expanded','true');});
$('month-picker-close').addEventListener('click',()=>$('month-picker').close());
$('month-picker').addEventListener('close',()=>{$('month-picker-open').setAttribute('aria-expanded','false');$('month-picker-open').focus();});
document.addEventListener('click',event=>{if($('month-picker').open&&!$('month-picker').contains(event.target)&&!$('month-picker-open').contains(event.target))$('month-picker').close();});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('month-picker').open)$('month-picker').close();});
$('year-prev').addEventListener('click',()=>{pickerYear=Math.max(1,pickerYear-1);picker();});$('year-next').addEventListener('click',()=>{pickerYear=Math.min(Number(today.slice(0,4)),pickerYear+1);picker();});
$('library-retry').addEventListener('click',()=>retry?.());window.addEventListener('popstate',()=>load(libraryState(location.search,today)));
for(const button of document.querySelectorAll('.coming-soon'))button.addEventListener('click',()=>dialog(`${button.dataset.feature}은 준비 중이에요`,'지금은 홈과 서재에서 당신의 이야기를 남겨보세요.'));
async function account(){const choice=await dialog('나의 계정',`${localStorage.getItem('nickname')||'나'}님\n이야기는 로그인한 계정에만 보관돼요.`,[{label:'홈페이지',value:'home'},{label:'닫기',value:'cancel'},{label:'로그아웃',value:'logout',primary:true}]);if(choice==='logout')await logout();else if(choice==='home')location.assign('/');}
$('account').addEventListener('click',account);$('settings').addEventListener('click',account);
function connect(){if(!same()||!token()||!uid)return;socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws/${encodeURIComponent(uid)}`);socket.onopen=()=>{if(same())socket.send(JSON.stringify({type:'authenticate',token:identity}));};socket.onmessage=event=>{if(!same())return;try{const data=JSON.parse(event.data);window.dispatchEvent(new Event('daily:socket'));if(['encourage_available','encourage_unavailable','seven_day_report'].includes(data.type)&&state?.view==='shelf')void loadCards();}catch{}};socket.onclose=event=>{if(![1000,1008].includes(event.code)&&same())reconnect=setTimeout(connect,5000);};}
window.addEventListener('space:identity-cleared',()=>{sequence++;cardSequence++;controller?.abort();clearPhotos();socket?.close(1000);clearTimeout(reconnect);for(const name of ['books','calendar-days','diary-list'])$(name).replaceChildren();$('letter-status').textContent='';$('weekly-preview').replaceChildren();});
window.addEventListener('pagehide',()=>{controller?.abort();clearPhotos();socket?.close(1000);clearTimeout(reconnect);});
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&state&&!$('month-picker').open)void load(state);});
if(!token())void expire();else{void load();connect();}
