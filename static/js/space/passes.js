import {$,json,node,id,token,owner,expire} from './ui.js?v=20261103-7c';
const identity=token(),uid=owner(),same=()=>token()===identity&&owner()===uid;
let saving=false,pending=null;
const names={dialogue:'추가 대화 하루 2회',encouragement:'설정 시각의 저녁 응원',weekly:'주간 차트·회고'};
const date=value=>value?new Intl.DateTimeFormat('ko-KR',{year:'numeric',month:'long',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Seoul'}).format(new Date(value+'+09:00')):'';
async function load(){
 $('access-error').hidden=true;
 try{const data=await json('/account/access');if(!same())return;
  $('access-title').textContent=data.trial_state==='active'?'슈퍼패스 무료 체험 중':'무료 이용 중';
  $('access-period').textContent=data.trial_state==='active'?`체험 종료: ${date(data.trial_expires_at)} (한국 시간)` :data.trial_state==='expired'?'7일 체험이 종료되어 무료로 전환됐어요. 기본 일기와 기억은 계속 이용할 수 있어요.':'기본 일기와 기억은 계속 무료로 이용할 수 있어요.';
  $('access-features').textContent=data.features.length?`이용 가능: ${data.features.map(f=>names[f]).join(' · ')}`:'체험 혜택인 추가 대화·저녁 응원·주간 차트는 새로 제공하지 않아요. 기존 결과는 계속 볼 수 있어요.';
  $('plan-cards').replaceChildren();
  for(const plan of data.plans){const card=node('article','plan-card'),heading=node('h3','',plan.label),description=node('p','',plan.features.length?plan.features.map(f=>names[f]).join('\n'):'기본 대화 1회와 일기\n폐기 후 기본 대화 복구\n기본 기억·기존 결과 열람');card.append(heading,description);if(data.trial_state==='active'&&plan.id==='super')card.append(node('span','selected','체험 중인 구성'));else if(data.trial_state!=='active'&&plan.id==='free')card.append(node('span','selected','현재 이용권'));
   const button=node('button','secondary',plan.id===data.selected_plan?'선택한 이용권':plan.id==='free'?'무료 유지 선택':'체험 후 이 조합 선택');button.disabled=saving||plan.id===data.selected_plan;button.setAttribute('aria-label',`${plan.label} 선택`);button.addEventListener('click',()=>choose(plan.id));card.append(button);$('plan-cards').append(card);}
  $('choice-status').textContent=data.selected_plan?`선택한 이용권: ${data.plans.find(p=>p.id===data.selected_plan)?.label} · 결제·권한 변경 없이 의향만 저장했어요.`:'체험 후 이용하고 싶은 조합을 선택해 주세요. 나중에 바꿀 수 있어요.';
 }catch(exc){if(same()&&exc.status!==401){$('access-error').hidden=false;$('access-error-message').textContent=exc.message;}}
}
async function choose(plan){
 if(saving||!same())return;saving=true;
 for(const button of $('plan-cards').querySelectorAll('button'))button.disabled=true;
 if(!pending||pending.plan!==plan)pending={request_id:id(),plan};
 try{await json('/account/plan-choice',{method:'POST',data:pending});if(!same())return;pending=null;}
 catch(exc){if(same()&&exc.status!==401){$('access-error').hidden=false;$('access-error-message').textContent=exc.message;}}
 finally{saving=false;if(same()){for(const button of $('plan-cards').querySelectorAll('button'))button.disabled=false;}}
 if(!pending&&same())await load();
}
$('access-retry').addEventListener('click',load);
window.addEventListener('space:identity-cleared',()=>{$('plan-cards').replaceChildren();$('access-title').textContent='';$('access-period').textContent='';$('access-features').textContent='';$('choice-status').textContent='';});
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')void load();});
if(!identity)void expire();else void load();
