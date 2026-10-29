// 실제 가입 스크립트를 HTTPS/별도 포트 출처에서 실행. 네트워크·사용자 DB 없음.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/register.js'), 'utf8');

async function scenario(origin, result) {
  const calls = [], alerts = [];
  let submit;
  const form = { addEventListener(name, fn) { if (name === 'submit') submit = fn; } };
  const window = { location: { origin, href: `${origin}/register` } };
  const context = vm.createContext({ window, console,
    document: { getElementById: id => id === 'registerForm' ? form : null },
    FormData: class { get(key) { return {username:'synthetic',password:'Test12!ab',
      email:'synthetic@example.org',nickname:'합성'}[key]; } },
    alert: value => alerts.push(value),
    fetch: async (url, options) => {
      calls.push({url: new URL(url, origin).href, options});
      if (result instanceof Error) throw result;
      return result;
    }
  });
  vm.runInContext(source, context);
  await submit.call(form, { preventDefault() {} });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `${origin}/register`);
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(JSON.parse(calls[0].options.body).username, 'synthetic');
  return {window, alerts};
}

(async () => {
  for (const origin of ['https://diary.example.org', 'http://127.0.0.1:8012']) {
    const success = await scenario(origin, {ok:true,json:async()=>({message:'가입 성공'})});
    assert.equal(success.window.location.href, '/login');
    assert.deepEqual(success.alerts, ['가입 성공']);
    const duplicate = await scenario(origin, {ok:false,json:async()=>({detail:'이미 사용 중인 아이디입니다.'})});
    assert.deepEqual(duplicate.alerts, ['이미 사용 중인 아이디입니다.']);
    assert.equal(duplicate.window.location.href, `${origin}/register`);
    const invalid = await scenario(origin, {ok:false,json:async()=>({detail:[{msg:'입력 오류'}]})});
    assert.deepEqual(invalid.alerts, ['입력 오류']);
    const offline = await scenario(origin, new Error('offline'));
    assert.match(offline.alerts[0], /서버와의 통신에 실패/);
  }
  console.log('Bundle 1 registration frontend: 8 scenarios passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
