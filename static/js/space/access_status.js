import {json,node,token,owner,dialog} from './ui.js?v=20261103-7c';
const identity=token(),uid=owner(),same=()=>token()===identity&&owner()===uid;
let running=false,welcoming=false,welcomeAttempted=false,stopped=false;
const pages=['/','/space','/library','/passes','/weekly','/letters'];
const label=value=>new Intl.DateTimeFormat('ko-KR',{month:'long',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Seoul'}).format(new Date(value+'+09:00'));
async function welcome(data){
 if(welcoming)return;welcoming=true;
 try{
  if(await dialog('7일 무료 체험을 시작해요',`가입일을 포함한 7일 동안 슈퍼패스 기능을 이용해요.\n체험 종료: ${label(data.trial_expires_at)} (한국 시간)`,[{label:'다음',value:'next',primary:true}])!=='next'||!same())return;
  if(await dialog('전등이와 함께 기록해 보세요','이야기를 남기고 전등을 누르면 답변해요. 기본 1회와 하루 추가 2회, 원하는 시각의 저녁 응원, 조건을 채운 주간 차트를 체험해요.\n주간은 첫 대화부터 7일·최소 3개 날짜의 하루 분석이 필요하며 체험이 자동 연장되지는 않아요.',[{label:'응원 시간 정하기',value:'settings',primary:true}])!=='settings'||!same())return;
  const {settings}=await import('./daily.js?v=20261103-10g7');await settings({waitForClose:true});
  // 시간 저장에 성공했을 때만 다음 방문의 자동 안내를 마친다.
  const preference=await json('/daily/settings');if(same()&&preference.configured)await json('/account/onboarding',{method:'POST'});
 }finally{welcoming=false;}
}
async function refresh(){
 if(running||!same()||stopped)return;running=true;
 try{const data=await json('/account/access');if(!same())return;
  let banner=document.getElementById('access-banner');
  if(!banner){banner=node('section','access-banner');banner.id='access-banner';const main=document.querySelector('main');main?.prepend(banner);}
  banner.replaceChildren();const message=data.trial_state==='active'?`슈퍼패스 무료 체험 · ${label(data.trial_expires_at)} 종료`:data.trial_state==='expired'?'7일 체험이 끝나 무료로 전환됐어요. 기본 일기와 기억은 계속 이용할 수 있어요.':'무료로 이용 중 · 기본 일기와 기억은 계속 이용할 수 있어요.';
  banner.append(node('span','',message+' '));const link=node('a','','이용권 살펴보기');link.href='/passes';banner.append(link);
  if(['/','/space'].includes(location.pathname)&&!data.onboarding_complete&&data.trial_state==='active'&&!welcomeAttempted){welcomeAttempted=true;void welcome(data);}
 }catch{/* 작성·열람은 이용 상태 안내의 연결 실패와 독립적으로 유지한다. */}
 finally{running=false;}
}
if(identity&&pages.includes(location.pathname)){void refresh();window.addEventListener('daily:clock',()=>void refresh());}
window.addEventListener('space:identity-cleared',()=>{stopped=true;document.getElementById('access-banner')?.remove();});
window.addEventListener('pagehide',()=>{stopped=true;});
