import {owner,token} from './ui.js?v=20261104-ui2';

const recorded = new Set();

export function recordWritingView(event, fields) {
  const identity = token();
  if (!identity) return;
  const key = `space:${owner()}:analytics:${event}:${fields.diary_id ?? ''}:${fields.navigation_id ?? fields.visit_id ?? ''}`;
  if (recorded.has(key)) return;
  try {
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, '1');
  } catch {}
  recorded.add(key);
  void fetch('/writing/analytics/view', {
    method: 'POST',
    headers: {Authorization: `Bearer ${identity}`, 'Content-Type': 'application/json'},
    body: JSON.stringify({event, ...fields}),
    keepalive: true
  }).catch(() => {
    recorded.delete(key);
    try {sessionStorage.removeItem(key);} catch {}
  });
}
