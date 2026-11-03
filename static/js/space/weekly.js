import {$,json,node,token,owner,expire} from './ui.js?v=20261103-7c';
import {chart,closeDetail} from './weekly_chart.js?v=20261103-7c';
import {weeklyModel} from './weekly_model.js?v=20261103-7c';
const identity=token(),uid=owner(),same=()=>identity===token()&&uid===owner();let sequence=0,notifyRetry=null,ready=false;
const names=['flow','emotion','keyword'];
function tab(name,focus=false){for(const value of names){const selected=value===name,button=$('tab-'+value);button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;$('panel-'+value).hidden=!selected||!ready;if(selected&&focus)button.focus();}}
for(const [index,name]of names.entries()){$('tab-'+name).addEventListener('click',()=>tab(name));$('tab-'+name).addEventListener('keydown',event=>{let next;if(event.key==='ArrowRight')next=(index+1)%3;else if(event.key==='ArrowLeft')next=(index+2)%3;else if(event.key==='Home')next=0;else if(event.key==='End')next=2;if(next!==undefined){event.preventDefault();tab(names[next],true);}});}
function block(root,title,text){if(!text)return;const section=node('section','weekly-copy-block');section.append(node('h2','',title),node('p','',Array.isArray(text)?text.join('\n'):text));root.append(section);}
function clear(){ready=false;for(const name of names)$('panel-'+name).hidden=true;$('weekly-empty').hidden=true;closeDetail();for(const name of ['weekly-chart','weekly-flow-copy','weekly-emotion-copy','weekly-days','weekly-keywords','weekly-keyword-copy'])$(name).replaceChildren();$('weekly-period').textContent='';}
async function load(){const current=++sequence;notifyRetry=null;clear();$('weekly-status').textContent='주간 기록을 불러오고 있어요.';$('weekly-retry').hidden=true;$('weekly-retry').textContent='다시 불러오기';
 try{const data=await json('/study/weekly/latest');if(!same()||current!==sequence)return;const m=weeklyModel(data);
  $('weekly-period').textContent=`${m.weekly.period_start||m.weekly.start_date} ~ ${m.weekly.period_end||m.weekly.end_date} · 대화 분석 ${m.days.length}일`;
  ready=true;tab(names.find(name=>$('tab-'+name).getAttribute('aria-selected')==='true')||'flow');
  $('weekly-chart').append(chart(m.points,m.days,same));block($('weekly-emotion-copy'),'주요 경향',m.emotion.trend);
  block($('weekly-emotion-copy'),'지배적 감정',m.emotion.dominant_emotion);block($('weekly-emotion-copy'),'추천사항',m.emotion.recommendation);block($('weekly-emotion-copy'),'주간 종합 평가',m.overall.overall_assessment);
  for(const word of m.keyword.main_themes||[])$('weekly-keywords').append(node('span','weekly-chip',word));
  block($('weekly-keyword-copy'),'반복된 이야기',m.keyword.recurring_patterns);block($('weekly-keyword-copy'),'주요 인사이트',m.keyword.insights);
  $('weekly-status').textContent='';
  // 화면이 실제 그려지고 연결된 경우에만 기존 완료 API와 호환한다.
  async function notify(){if(!same()||current!==sequence||!$('weekly-chart').querySelector('svg')?.isConnected)return;try{await json('/study/chart-loading-complete',{method:'POST',data:{analysis_id:m.weekly.id,status:'completed',week_start_date:m.weekly.start_date,week_end_date:m.weekly.end_date}});if(same()&&current===sequence){notifyRetry=null;$('weekly-status').textContent='';$('weekly-retry').hidden=true;}}catch(exc){if(same()&&current===sequence){notifyRetry=notify;$('weekly-status').textContent='차트는 표시됐지만 완료 알림을 보내지 못했어요.';$('weekly-retry').textContent='완료 알림 다시 보내기';$('weekly-retry').hidden=false;}}}
  requestAnimationFrame(()=>void notify());
 }catch(exc){if(!same()||current!==sequence||exc.status===401)return;clear();$('weekly-empty').hidden=exc.status!==404;$('weekly-status').textContent=exc.status===404?'':exc.message;$('weekly-retry').hidden=exc.status===404;}}
$('weekly-retry').addEventListener('click',()=>notifyRetry?notifyRetry():load());window.addEventListener('space:identity-cleared',()=>{sequence++;notifyRetry=null;clear();$('weekly-status').textContent='';});
if(!token())void expire();else void load();
