import {token,json,node,dialog,logout,clearIdentity} from './ui.js?v=20261103-5d';
let authenticated=false;
async function header(){if(!token())return;const observedToken=token();try{
 const user=await json('/account/me',{authRedirect:false});authenticated=true;
 const avatar=document.createElementNS('http://www.w3.org/2000/svg','svg');avatar.classList.add('icon');const use=document.createElementNS('http://www.w3.org/2000/svg','use');use.setAttribute('href','#i-user');avatar.append(use);
 const name=node('span','',`${user.nickname}님`),divider=node('span','header-divider'),button=node('button','','로그아웃');button.addEventListener('click',logout);document.getElementById('account-header').replaceChildren(avatar,name,divider,button);
 }catch(error){if(error.status===401&&token()===observedToken)clearIdentity();}}
document.getElementById('enter-space').addEventListener('click',async()=>{
 if(authenticated){location.assign('/space');return;}
 if(token()){try{await json('/account/me');location.assign('/space');return;}catch(error){if(error.status!==401)await dialog('잠시 연결이 어려워요',error.message);return;}}
 const answer=await dialog('로그인이 필요한 화면입니다','나의 공간에 들어가려면 로그인해 주세요.');if(answer==='ok')location.assign('/login');
});
void header();
