import {owner,token} from './ui.js?v=20261104-ui2';

const recorded = new Set();

export function recordWritingView(event, fields) {
  recordWritingSignal('/writing/analytics/view', event, fields,
    fields.diary_id ?? '', fields.navigation_id ?? fields.visit_id ?? '');
}

export function recordExtraOpportunity(writingId, day) {
  recordWritingSignal(`/writing/${writingId}/analytics/extra-opportunity`, 'extra_reply_available', {}, day);
}

export function recordReplyObservation(writingId, event, fields) {
  recordWritingSignal(`/writing/${writingId}/analytics/reply`, event, fields, fields.attempt_id);
}

export function recordWeeklyView(weeklyId, visitId, surface) {
  if (!Number.isInteger(weeklyId) || weeklyId <= 0) return;
  recordWritingSignal('/study/weekly/analytics/view', 'weekly_view',
    {weekly_id: weeklyId, visit_id: visitId, surface}, weeklyId, visitId, surface);
}

function recordWritingSignal(path, event, fields, ...parts) {
  const identity = token();
  if (!identity) return;
  const key = `space:${owner()}:analytics:${event}:${parts.join(':')}`;
  if (recorded.has(key)) return;
  try {
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, '1');
  } catch {}
  recorded.add(key);
  void fetch(path, {
    method: 'POST',
    headers: {Authorization: `Bearer ${identity}`, 'Content-Type': 'application/json'},
    body: JSON.stringify({event, ...fields}),
    keepalive: true
  }).then(response => {
    if (!response.ok) throw new Error('Analytics request failed');
  }).catch(() => {
    recorded.delete(key);
    try {sessionStorage.removeItem(key);} catch {}
  });
}
