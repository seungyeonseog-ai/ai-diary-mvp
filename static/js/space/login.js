import {clearIdentity} from './ui.js?v=20261103-7a';
const form=document.getElementById('loginForm'),error=document.getElementById('login-error'),username=document.getElementById('username');
const remembered=localStorage.getItem('remembered_id');if(remembered){username.value=remembered;document.getElementById('rememberId').checked=true;}
form.addEventListener('submit',async event=>{
 event.preventDefault();const button=form.querySelector('button[type=submit]');button.disabled=true;error.textContent='';
 try{
  const response=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:username.value,password:document.getElementById('password').value})});
  const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'아이디와 비밀번호를 확인해 주세요.');
  clearIdentity();localStorage.setItem('access_token',data.access_token);localStorage.setItem('nickname',data.nickname);localStorage.setItem('user_id',String(data.user_id));
  if(document.getElementById('rememberId').checked)localStorage.setItem('remembered_id',username.value);else localStorage.removeItem('remembered_id');
  location.assign('/');
 }catch(failure){error.textContent=failure instanceof TypeError?'연결하지 못했어요. 잠시 후 다시 시도해 주세요.':failure.message;}
 finally{button.disabled=false;}
});
