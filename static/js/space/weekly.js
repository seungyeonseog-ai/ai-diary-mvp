import {$,json,node,token,owner,expire} from './ui.js?v=20261103-7a';
import {weeklyModel} from './weekly_model.js?v=20261103-7a';
const identity=token(),uid=owner(),same=()=>identity===token()&&uid===owner();let sequence=0,notifyRetry=null;
const names=['flow','emotion','keyword'];
function tab(name,focus=false){for(const value of names){const selected=value===name,button=$('tab-'+value);button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;$('panel-'+value).hidden=!selected;if(selected&&focus)button.focus();}}
for(const [index,name]of names.entries()){$('tab-'+name).addEventListener('click',()=>tab(name));$('tab-'+name).addEventListener('keydown',event=>{let next;if(event.key==='ArrowRight')next=(index+1)%3;else if(event.key==='ArrowLeft')next=(index+2)%3;else if(event.key==='Home')next=0;else if(event.key==='End')next=2;if(next!==undefined){event.preventDefault();tab(names[next],true);}});}
function block(root,title,text){if(!text)return;const section=node('section','weekly-copy-block');section.append(node('h2','',title),node('p','',Array.isArray(text)?text.join('\n'):text));root.append(section);}
function chart(points){const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 720 300');svg.setAttribute('role','img');svg.setAttribute('aria-label','분석된 날짜별 감정 흐름');
 const add=(tag,attrs,text)=>{const element=document.createElementNS(ns,tag);for(const [key,value]of Object.entries(attrs))element.setAttribute(key,value);if(text!==undefined)element.textContent=text;svg.append(element);return element;};
 const extent=Math.max(1,...points.map(p=>Math.abs(p.value))),y=value=>140-value/extent*100;
 for(const value of [-extent,0,extent]){add('line',{x1:45,y1:y(value),x2:690,y2:y(value),stroke:'#ddc5a9'});add('text',{x:6,y:y(value)+5,fill:'#8c7059','font-size':13},value.toFixed(1));}
 const positions=points.map((p,i)=>({x:points.length===1?360:55+i*625/(points.length-1),y:y(p.value)}));
 add('polyline',{points:positions.map(p=>`${p.x},${p.y}`).join(' '),fill:'none',stroke:'#d58c58','stroke-width':3});
 positions.forEach((p,i)=>{add('circle',{cx:p.x,cy:p.y,r:5,fill:'#c67c4b'});add('text',{x:p.x,y:275,'text-anchor':'middle',fill:'#82634b','font-size':14},points[i].date.slice(5).replace('-','/'));});return svg;}
function clear(){for(const name of ['weekly-chart','weekly-flow-copy','weekly-emotion-copy','weekly-days','weekly-keywords','weekly-keyword-copy'])$(name).replaceChildren();$('weekly-period').textContent='';}
async function load(){const current=++sequence;notifyRetry=null;clear();$('weekly-status').textContent='주간 기록을 불러오고 있어요.';$('weekly-retry').hidden=true;
 try{const data=await json('/study/weekly/latest');if(!same()||current!==sequence)return;const m=weeklyModel(data);
  $('weekly-period').textContent=`${m.weekly.period_start||m.weekly.start_date} ~ ${m.weekly.period_end||m.weekly.end_date} · 대화 분석 ${m.days.length}일`;
  $('weekly-chart').append(chart(m.points));block($('weekly-flow-copy'),'마음의 흐름',m.emotion.trend);
  block($('weekly-emotion-copy'),'눈에 띈 감정',m.emotion.dominant_emotion);block($('weekly-emotion-copy'),'마음을 위한 제안',m.emotion.recommendation);block($('weekly-emotion-copy'),'한 주를 돌아보며',m.overall.overall_assessment);
  for(const day of m.days){const section=node('section','weekly-day');section.append(node('h3','',day.date_str),node('p','',typeof day.summary==='string'?day.summary:''));$('weekly-days').append(section);}
  for(const word of m.keyword.main_themes||[])$('weekly-keywords').append(node('span','weekly-chip',word));
  block($('weekly-keyword-copy'),'반복된 이야기',m.keyword.recurring_patterns);block($('weekly-keyword-copy'),'기록에서 발견한 점',m.keyword.insights);
  $('weekly-status').textContent='';
  // 화면이 실제 그려지고 연결된 경우에만 기존 완료 API와 호환한다.
  async function notify(){if(!same()||current!==sequence||!$('weekly-chart').querySelector('svg')?.isConnected)return;try{await json('/study/chart-loading-complete',{method:'POST',data:{analysis_id:m.weekly.id,status:'completed',week_start_date:m.weekly.start_date,week_end_date:m.weekly.end_date}});if(same()&&current===sequence){notifyRetry=null;$('weekly-status').textContent='';$('weekly-retry').hidden=true;}}catch(exc){if(same()&&current===sequence){notifyRetry=notify;$('weekly-status').textContent='차트는 표시됐지만 완료 알림을 보내지 못했어요.';$('weekly-retry').textContent='완료 알림 다시 보내기';$('weekly-retry').hidden=false;}}}
  requestAnimationFrame(()=>void notify());
 }catch(exc){if(!same()||current!==sequence||exc.status===401)return;clear();$('weekly-status').textContent=exc.status===404?'아직 생성된 주간 기록이 없어요. 7일 기간이 끝나면 대화한 날짜가 3일 이상인지 확인해요.':exc.message;$('weekly-retry').hidden=exc.status===404;}}
$('weekly-retry').addEventListener('click',()=>notifyRetry?notifyRetry():load());window.addEventListener('space:identity-cleared',()=>{sequence++;notifyRetry=null;clear();$('weekly-status').textContent='';});
if(!token())void expire();else void load();
