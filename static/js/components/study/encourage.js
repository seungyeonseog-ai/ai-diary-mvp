// --- 그대로 유지 ---
function typewriterEffect(text, element) {
  if (!element) return;
  element.textContent = '';
  element.style.whiteSpace = 'pre-wrap';
  const textNode = document.createTextNode('');
  element.appendChild(textNode);
  let i = 0;
  (function type() {
    if (i < text.length) {
      textNode.appendData(text.charAt(i++));
      setTimeout(type, 50);
    }
  })();
}

let lastLetter = null;
let letterRequest = null;
const letterReasons = {
  insufficient:'오늘 응원 편지를 만들기에는 대화가 부족합니다.',
  waiting_time:'응원 편지는 오전 10시 이후 생성됩니다.',
  pending:'응원 편지를 준비하고 있습니다. 잠시 후 다시 확인해 주세요.',
  loading:'오늘의 응원 편지를 확인하고 있습니다.',
  error:'응원 편지를 불러오지 못했습니다. 다시 불러오기를 눌러 주세요.'
};

function isToday(ts) {
  if (!ts || Number.isNaN(new Date(ts).getTime())) return false;
  const date = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Seoul',
    year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(ts));
  const today = window.studyState?.today() || new Intl.DateTimeFormat('en-CA', {
    timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  return date === today;
}

function clearLetterCache() {
  for (const key of ['encourage_content','encourage_timestamp','encourage_date','encourage_result_id','encourage_owner']) {
    localStorage.removeItem(key);
  }
}

function renderEncourageFromLocalStorage() {
  const element = document.getElementById('encourage-message');
  if (!element) return;
  const content = localStorage.getItem('encourage_content');
  const ts = localStorage.getItem('encourage_timestamp');
  const owner = localStorage.getItem('encourage_owner');
  if (!isToday(ts) || (owner && owner !== localStorage.getItem('user_id'))) {
    element.textContent = '';
    clearLetterCache();
    return;
  }
  element.textContent = content || '';
  element.style.whiteSpace = 'pre-wrap';
  element.style.display = 'block';
}

function showLetterState(state) {
  const btn = document.getElementById('encourage-btn');
  const msg = document.getElementById('encourage-message');
  if (!btn || !msg) return;
  const active = state === 'ready' || state === 'error';
  btn.classList.toggle('disabled', !active);
  btn.classList.toggle('active', active);
  btn.setAttribute('aria-disabled', String(!active));
  btn.setAttribute('type', 'button');
  btn.dataset.state = state;
  btn.textContent = state === 'ready' ? '응원 편지 다시 보기' : state === 'error' ? '다시 불러오기' : '응원 메시지 받기';
  if (state !== 'ready') {
    msg.textContent = letterReasons[state] || letterReasons.insufficient;
    delete msg.dataset.resultKey;
  }
}

async function syncEncouragement(status) {
  const element = document.getElementById('encourage-message');
  if (!element || !status || String(status.user_id) !== localStorage.getItem('user_id')) return;
  const letter = status.encouragement;
  if (letter.state !== 'ready') {
    lastLetter = null;
    clearLetterCache();
    showLetterState(letter.state);
    return;
  }
  const token = localStorage.getItem('access_token');
  const key = `${status.user_id}|${status.server_date}|${letter.id}`;
  if (lastLetter?.key === key && lastLetter.token === token) {
    showLetterState('ready');
    if (element.dataset.resultKey !== key) {
      element.textContent = lastLetter.data.encourage_content;
      element.style.whiteSpace = 'pre-wrap';
      element.dataset.resultKey = key;
    }
    return;
  }
  if (letterRequest?.key === key && letterRequest.token === token) return letterRequest.promise;
  showLetterState('loading');
  const promise = (async () => {
    try {
      const response = await fetch('/study/encourage', {headers:{Authorization:`Bearer ${token}`}, cache:'no-store'});
      if (!response.ok) throw new Error('letter_unavailable');
      const data = await response.json();
      if (localStorage.getItem('access_token') !== token || String(status.user_id) !== localStorage.getItem('user_id')) return;
      const current = window.studyState.current();
      if (data.date !== window.studyState.today() || data.date !== current?.server_date || data.id !== current?.encouragement.id) {
        window.studyState.refresh(true);
        return;
      }
      lastLetter = {key, data, token};
      localStorage.setItem('encourage_content', data.encourage_content);
      localStorage.setItem('encourage_timestamp', data.timestamp);
      localStorage.setItem('encourage_date', data.date);
      localStorage.setItem('encourage_result_id', String(data.id));
      localStorage.setItem('encourage_owner', String(status.user_id));
      const currentElement = document.getElementById('encourage-message');
      if (currentElement) {
        currentElement.textContent = data.encourage_content;
        currentElement.style.whiteSpace = 'pre-wrap';
        currentElement.dataset.resultKey = key;
        showLetterState('ready');
      }
      window.globalNotificationManager?.updateNotification('encourage_unavailable', {
        type:'encourage_unavailable', date:data.date, result_id:data.id});
    } catch (_) {
      if (localStorage.getItem('access_token') === token) showLetterState('error');
    } finally {
      if (letterRequest?.key === key && letterRequest.token === token) letterRequest = null;
    }
  })();
  letterRequest = {key, promise, token};
  return promise;
}

async function handleEncourageClick() {
  const status = await window.studyState.refresh();
  await syncEncouragement(status);
  if (status?.encouragement.state === 'ready' && lastLetter) {
    typewriterEffect(lastLetter.data.encourage_content, document.getElementById('encourage-message'));
  }
}
window.handleEncourageClick = handleEncourageClick;

function bindEncourageGlobalListenersOnce() {
  if (window.__encourageListenersBound) return;
  window.__encourageListenersBound = true;
  document.addEventListener('click', event => {
    if (event.target.closest('#encourage-btn')) handleEncourageClick();
  }, {capture:true});
  document.addEventListener('study_state_updated', event => syncEncouragement(event.detail));
  document.addEventListener('study_state_error', () => showLetterState('error'));
  document.addEventListener('diary_reset', () => {
    lastLetter = null;
    clearLetterCache();
    showLetterState('loading');
  });
}

window.initEncourageUI = async function() {
  bindEncourageGlobalListenersOnce();
  showLetterState('loading');
  const status = await window.studyState.refresh();
  return syncEncouragement(status);
};
