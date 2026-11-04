import {json,node,token,owner,dialog} from './ui.js?v=20261104-ui2';
const identity=token(),uid=owner(),same=()=>token()===identity&&owner()===uid;
let running=false,welcoming=false,welcomeAttempted=false,stopped=false;
const pages=['/','/space','/library','/passes','/weekly','/letters'];
const label=value=>new Intl.DateTimeFormat('ko-KR',{month:'long',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Seoul'}).format(new Date(value+'+09:00'));
async function welcome(data){
 if(welcoming)return;welcoming=true;
 try{
  if(await dialog('7일 무료 체험을 시작해요',`가입일을 포함한 7일 동안 슈퍼패스 기능을 이용해요.\n체험 종료: ${label(data.trial_expires_at)} (한국 시간)`,[{label:'다음',value:'next',primary:true}],{dismissible:false})!=='next'||!same())return;
  const {settings}=await import('./daily.js?v=20261104-ui2');await settings({waitForClose:true});
  // 시간 저장에 성공했을 때만 다음 방문의 자동 안내를 마친다.
  const preference=await json('/daily/settings');if(same()&&preference.configured)await json('/account/onboarding',{method:'POST'});
 }finally{welcoming=false;}
}
async function refresh(){
 if(running||!same()||stopped)return;running=true;
 try{const data=await json('/account/access');if(!same())return;
  document.getElementById('access-banner')?.remove();
  const accessLabel=data.trial_state==='active'?'슈퍼패스':'무료';
  document.body.dataset.accessLabel=accessLabel;
  for(const id of ['home-pass-badge','sidebar-pass-badge']){const badge=document.getElementById(id);if(badge){badge.textContent=accessLabel;badge.hidden=false;}}
  if(['/','/space'].includes(location.pathname)&&!data.onboarding_complete&&data.trial_state==='active'&&!welcomeAttempted){welcomeAttempted=true;void welcome(data);}
 }catch{/* 작성·열람은 이용 상태 안내의 연결 실패와 독립적으로 유지한다. */}
 finally{running=false;}
}
if(identity&&(pages.includes(location.pathname)||/^\/diary\/[1-9]\d*$/.test(location.pathname))){void refresh();window.addEventListener('daily:clock',()=>void refresh());}
window.addEventListener('space:identity-cleared',()=>{stopped=true;delete document.body.dataset.accessLabel;document.getElementById('access-banner')?.remove();for(const id of ['home-pass-badge','sidebar-pass-badge']){const badge=document.getElementById(id);if(badge){badge.textContent='';badge.hidden=true;}}});
window.addEventListener('pagehide',()=>{stopped=true;});
