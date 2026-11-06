import {token,json,node,dialog,logout,clearIdentity} from './ui.js?v=20261104-ui2';
let authenticated=false;
async function header(){if(!token())return;const observedToken=token();try{
 const user=await json('/account/me',{authRedirect:false});authenticated=true;
 const avatar=document.createElementNS('http://www.w3.org/2000/svg','svg');avatar.classList.add('icon');const use=document.createElementNS('http://www.w3.org/2000/svg','use');use.setAttribute('href','#i-user');avatar.append(use);
 const name=node('span','',`${user.nickname}님`),account=node('span','header-account-name'),badge=node('span','pass-badge');badge.id='home-pass-badge';badge.textContent=document.body.dataset.accessLabel||'';badge.hidden=!badge.textContent;account.append(badge,name);
 const divider=node('span','header-divider'),button=node('button','','로그아웃');button.addEventListener('click',logout);document.getElementById('account-header').replaceChildren(avatar,account,divider,button);
 }catch(error){if(error.status===401&&token()===observedToken)clearIdentity();}}
document.getElementById('enter-space').addEventListener('click',async()=>{
 if(authenticated){location.assign('/space');return;}
 // 공간의 실제 API가 인증을 확인한다. 진입 전에 같은 인증 왕복을 반복하지 않는다.
 if(token()){location.assign('/space');return;}
 const answer=await dialog('로그인이 필요한 화면입니다','나의 공간에 들어가려면 로그인해 주세요.');if(answer==='ok')location.assign('/login');
});
void header();
