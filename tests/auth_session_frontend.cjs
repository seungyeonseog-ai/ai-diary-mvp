const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '..');
const authSource = fs.readFileSync(path.join(root, 'static/js/auth_session.js'), 'utf8');
const chatSource = fs.readFileSync(path.join(root, 'static/js/components/chatting/section.js'), 'utf8');

function makeContext(responses) {
  const calls = [], redirects = [], alerts = [], removed = [], bubbles = [];
  const input = {value: '아직 보내지 않은 글'};
  const box = {appendChild: item => bubbles.push(item)};
  const listeners = {};
  const storage = new Map([['access_token', 'synthetic-token'], ['nickname', 'tester']]);
  const window = {
    location: {origin: 'http://localhost:8000', href: 'http://localhost:8000/mypage_edit', pathname: '/mypage_edit', replace: url => redirects.push(url)},
    alert: message => alerts.push(message),
    fetch: async (url) => {
      calls.push(url);
      const next = responses.shift();
      if (next instanceof Error) throw next;
      return next || {status: 200, ok: true};
    },
  };
  const context = vm.createContext({window, URL, TextDecoder, Date,
    localStorage: {getItem: key => storage.get(key) || null, removeItem: key => {removed.push(key); storage.delete(key);}},
    document: {querySelector: () => null, addEventListener: (name, callback) => {listeners[name] = callback;},
      getElementById: id => id === 'input-field' ? input : box,
      createElement: () => ({style: {}})},
    alert: window.alert,
  });
  vm.runInContext(authSource, context);
  context.fetch = window.fetch;
  return {context, window, calls, redirects, alerts, removed, bubbles, input, listeners};
}

(async () => {
  let test = makeContext([{status: 401, ok: false}]);
  vm.runInContext(chatSource, test.context);
  await test.context.sendMessage();
  assert.deepEqual(test.calls, ['/chat/send']);
  assert.equal(test.bubbles.length, 0);
  assert.equal(test.input.value, '아직 보내지 않은 글');
  assert.deepEqual(test.redirects, ['/login']);
  assert.ok(test.removed.includes('access_token'));

  test = makeContext([{status: 200, ok: true, json: async () => ({turn: 1, session_id: 'synthetic'})}, {status: 401, ok: false}]);
  vm.runInContext(chatSource, test.context);
  await test.context.sendMessage();
  assert.equal(test.bubbles.length, 2); // 보낸 사용자 메시지와 시간만 표시
  assert.deepEqual(test.redirects, ['/login']);

  test = makeContext([{status: 401}, {status: 401}]);
  await test.window.fetch('/study/diary/generate/stream');
  await test.window.fetch('/chat/history');
  assert.equal(test.alerts.length, 1);
  assert.equal(test.redirects.length, 1);

  test = makeContext([{status: 500}, {status: 401}, new Error('offline')]);
  await test.window.fetch('/study/diary/check-condition');
  await test.window.fetch('https://example.test/chat/history');
  await assert.rejects(test.window.fetch('/chat/history'), /offline/);
  assert.equal(test.redirects.length, 0);

  test = makeContext([{status: 200, ok: true}]);
  await test.window.fetch('/study/diary/check-condition');
  assert.equal(test.removed.length, 0);
  assert.equal(test.redirects.length, 0);
  console.log('Auth frontend: 5 scenarios passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
