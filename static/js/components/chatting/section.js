let messages = [];
let turn = null;
let sessionId = null;

window.initChattingSection = async () => {
  // 로컬 시간 기준 오늘 날짜 표시
  const today = new Date().toLocaleDateString('ko-KR').replace(/\. /g, '-').replace(/\./g, '').replace(/-/g, '-');
  const dateElem = document.getElementById("chat-date");
  if (dateElem) dateElem.textContent = today;

  const token = localStorage.getItem("access_token");
  const headers = {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${token}`
  };
  const res = await fetch("/chat/history", {
    method: "POST",
    headers,
    body: JSON.stringify({ date: today })
  });
  if (!res.ok) return;
  const data = await res.json();
  messages = data.messages || [];
  messages.forEach(msg => renderBubble(msg.role, msg.message, msg.timestamp));

  // 전송 버튼 이벤트
  const sendBtn = document.querySelector("#input-box button");
  if (sendBtn) sendBtn.onclick = sendMessage;
};

let chatSending = false;
async function sendMessage() {
  const input = document.getElementById('input-field');
  const message = input.value.trim();
  if (!message || chatSending) return;
  const token = localStorage.getItem('access_token');
  const box = document.getElementById('chat-box');
  const button = document.querySelector('#input-box button');
  const current = () => localStorage.getItem('access_token') === token && document.getElementById('chat-box') === box;
  const headers = {'Content-Type':'application/json', 'Authorization':`Bearer ${token}`};
  chatSending = true;
  if (button) button.disabled = true;
  try {
    const sent = await fetch('/chat/send', {method:'POST', headers, body:JSON.stringify({message})});
    if (!sent.ok) {
      if (sent.status !== 401) alert('메시지를 보내지 못했습니다. 다시 시도해 주세요.');
      return;
    }
    const data = await sent.json();
    if (!current()) return;
    turn = data.turn;
    sessionId = data.session_id;
    input.value = '';
    renderBubble('user', message);
    messages.push({role:'user', message});
    const response = await fetch('/chat/response_stream', {
      method:'POST', headers:{...headers, Accept:'text/event-stream'}, body:JSON.stringify({turn, session_id:sessionId})
    });
    if (!current()) return;
    if (!response.ok) {
      if (response.status !== 401) alert('답변을 받지 못했습니다. 잠시 후 다시 시도해 주세요.');
      return;
    }
    await handleChatResponse(response, box, current);
  } catch (_) {
    if (current()) alert('통신이 끊겼습니다. 대화 기록에서 저장 여부를 확인해 주세요.');
  } finally {
    chatSending = false;
    if (button) button.disabled = false;
  }
}

async function handleChatResponse(response, box, current = () => true) {
  const bubble = document.createElement('div');
  bubble.className = 'bubble assistant';
  bubble.style.whiteSpace = 'pre-wrap';
  const status = document.createElement('span');
  status.className = 'message-time';
  status.textContent = '답변 생성 중…';
  box.appendChild(bubble);
  box.appendChild(status);
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let pending = '', content = '', saved = false, failed = false;
  function handle(frame) {
    const lines = frame.split('\n');
    const event = lines.find(line => line.startsWith('event:'))?.slice(6).trim();
    const dataLine = lines.find(line => line.startsWith('data:'));
    if (!dataLine) return;
    const data = JSON.parse(dataLine.slice(5));
    if (failed || saved) return;
    if (event === 'chunk') {
      content += data.text;
      bubble.textContent = content;
      box.scrollTop = box.scrollHeight;
    } else if (event === 'saved') {
      saved = true;
      status.textContent = '저장 완료';
      messages.push({role:'assistant', message:content});
    } else if (event === 'error') {
      failed = true;
      status.textContent = data.message;
      status.style.color = 'red';
      if (!content) bubble.textContent = '답변을 생성하지 못했습니다.';
    }
  }
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (!current()) { await reader.cancel(); return; }
      pending += done ? decoder.decode() : decoder.decode(value, {stream:true});
      pending = pending.replace(/\r\n/g, '\n');
      let boundary;
      while ((boundary = pending.indexOf('\n\n')) >= 0) {
        handle(pending.slice(0,boundary)); pending = pending.slice(boundary+2);
      }
      if (done) break;
    }
    if (pending.trim()) handle(pending);
  } catch (_) {
    if (!current()) return;
  } finally {
    if (current() && !saved && !failed) {
      status.textContent = '저장 완료를 확인하지 못했습니다. 대화 기록을 다시 확인해 주세요.';
      status.style.color = 'red';
    }
  }
}

function renderBubble(role, message, timestamp) {
  // 말풍선 생성
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.textContent = message;

  // 시간 표시 요소 생성
  const timeSpan = document.createElement("span");
  timeSpan.className = "message-time";

  // timestamp가 있으면 사용, 없으면 현재 시간
  const timeToShow = timestamp ? new Date(timestamp) : new Date();
  timeSpan.textContent = timeToShow.toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit'
  });

  // chat-box에 각각 독립적으로 추가
  const box = document.getElementById("chat-box");
  box.appendChild(bubble);
  box.appendChild(timeSpan);
  box.scrollTop = box.scrollHeight;
}
