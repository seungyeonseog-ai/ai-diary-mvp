// Node 내장 모듈만 사용. 실제 브라우저/API 접속 없이 활성 화면의 SSE 처리를 검사한다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/js/components/study/sub_diary_generate.js'), 'utf8');

async function run(stream) {
    const notices = [];
    const elements = {};
    const classes = new Set(['hidden']);
    for (const id of ['generation-indicator', 'ai-generated-text', 'generate-diary-btn']) {
        elements[id] = {textContent: '', disabled: false, classList: {
            add: c => classes.add(c), remove: c => classes.delete(c),
        }};
    }
    const context = vm.createContext({
        TextDecoder, console: {log() {}, error() {}},
        document: {getElementById: id => elements[id], addEventListener() {}, querySelectorAll: () => []},
        window: {popupManager: {show: message => notices.push(message)}},
    });
    vm.runInContext(source, context);
    // 한글 UTF-8 문자를 포함해 모든 바이트 경계를 끊어서 전달한다.
    const bytes = new TextEncoder().encode(stream);
    let index = 0;
    await context.handleStreamingResponse({body: {getReader: () => ({read: async () =>
        index < bytes.length ? {done: false, value: bytes.slice(index, ++index)} : {done: true},
    })}});
    assert.equal(elements['generate-diary-btn'].disabled, false);
    assert.ok(classes.has('hidden'));
    return {notices, text: elements['ai-generated-text'].textContent};
}

(async () => {
    let result = await run('event: chunk\ndata: {"text":"오늘\\n행복했다."}\n\nevent: saved\ndata: {"diary_id":42}\n\n');
    assert.equal(result.text, '오늘\n행복했다.');
    assert.match(result.notices[0], /완료/);
    result = await run('event: chunk\ndata: {"text":"일부 내용"}\n\n');
    assert.match(result.notices[0], /저장 완료를 확인하지 못했습니다/);
    result = await run('event: error\ndata: {"message":"저장 실패"}\n\n');
    assert.equal(result.notices[0], '저장 실패');
    console.log('Frontend SSE: 3 scenarios passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
