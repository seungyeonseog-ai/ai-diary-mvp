// M13: 실제 차트 모듈의 그리기 성공/실패와 완료 POST를 함께 검사한다.
const assert = require('node:assert/strict');
const {setup,weeklyData} = require('./bundle3_frontend.cjs');
const completions = t => t.calls.filter(c=>c.url==='/study/chart-loading-complete');
const status = t => t.ids.get('chart-restore-status')?.textContent || '';

(async()=>{
  let count=0;
  async function test(name, run) {await run();count++;console.log('PASS '+name);}
  await test('두 그래프의 그리기 후에만 완료 POST',async()=>{
    const t=setup();await t.window.initSevenChartUI();await t.flush();
    assert.equal(t.charts.size,2);
    assert.ok([...t.charts.values()].every(c=>c.drawn && c.config.options.animation===false));
    assert.equal(completions(t).length,1);
    const body=JSON.parse(completions(t)[0].opts.body);
    assert.equal(body.analysis_id,41);assert.equal(body.status,'completed');
    assert.equal(status(t),'');
    await t.window.studyState.refresh();await t.flush();
    assert.equal(completions(t).length,1);assert.equal(status(t),'');
  });
  await test('표시 전에 완료 함수 직접 호출해도 POST 없음',async()=>{
    const t=setup();assert.equal(await t.context.notifyChartLoadingComplete(41),false);
    assert.equal(completions(t).length,0);
  });
  await test('Chart.js 미로드 시 완료 없음·복구 후 재시도',async()=>{
    const t=setup();delete t.context.Chart;
    await t.window.initSevenChartUI();await t.flush();
    assert.equal(completions(t).length,0);assert.match(status(t),/라이브러리/);
    assert.equal(t.storage.has('seven_day_report_data'),false);
    t.context.Chart=t.chartClass;await t.window.studyState.refresh();await t.flush();
    assert.equal(completions(t).length,1);assert.equal(t.charts.size,2);
  });
  await test('빈 자료는 별도 안내·완료 없음',async()=>{
    const t=setup();const data=weeklyData();data.diary_analyses=[];t.setWeeklyData(data);
    await t.window.initSevenChartUI();await t.flush();
    assert.equal(completions(t).length,0);assert.equal(t.charts.size,0);
    assert.match(status(t),/표시할 일일 분석 자료가 없습니다/);
  });
  await test('점수 문자열/NaN/합산 무한대는 완료 없음',async()=>{
    for(const scores of [['bad'],[NaN],[Infinity],[1e308,1e308]]) {
      const t=setup();const data=weeklyData();data.diary_analyses[0].scores=scores;t.setWeeklyData(data);
      await t.window.initSevenChartUI();await t.flush();
      assert.equal(completions(t).length,0);assert.equal(t.charts.size,0);assert.match(status(t),/점수/);
    }
  });
  await test('손상된 날짜는 완료 없음',async()=>{
    const t=setup();const data=weeklyData();data.diary_analyses[0].date_str='not-a-date';t.setWeeklyData(data);
    await t.window.initSevenChartUI();await t.flush();assert.equal(completions(t).length,0);
  });
  await test('손상된 분석 JSON/숫자 속성은 완료 없음',async()=>{
    for(const mutate of [d=>d.weekly_analysis.keyword_patterns='invalid JSON',
      d=>d.weekly_analysis.keyword_patterns=null,
      d=>d.weekly_analysis.emotion_trend.emotion_stability='bad',
      d=>d.weekly_analysis.comprehensive_pattern_result={stress_level:NaN}]) {
      const t=setup();const data=weeklyData();mutate(data);t.setWeeklyData(data);
      await t.window.initSevenChartUI();await t.flush();assert.equal(completions(t).length,0);
    }
  });
  await test('누락된 두 번째 캔버스는 완료 없음',async()=>{
    const t=setup();t.ids.delete('radarChart');await t.window.initSevenChartUI();await t.flush();
    assert.equal(completions(t).length,0);assert.match(status(t),/화면을 찾지 못했습니다/);
  });
  await test('생성·그리기·context·크기 실패 후 부분 차트 정리',async()=>{
    for(const fault of ['constructor','second','draw','context','size']) {
      const t=setup();t.setChartFault(fault);await t.window.initSevenChartUI();await t.flush();
      assert.equal(completions(t).length,0);assert.equal(t.charts.size,0);
      assert.match(status(t),/차트를 표시하지 못했습니다/);
      assert.equal(t.storage.has('seven_day_report_data'),false);
      t.setChartFault(null);await t.window.studyState.refresh();await t.flush();
      assert.equal(t.charts.size,2);assert.equal(completions(t).length,1);
    }
  });
  await test('연결 끊긴 캔버스는 완료 없음',async()=>{
    const t=setup();t.ids.get('emotionTrendChart').isConnected=false;
    await t.window.initSevenChartUI();await t.flush();assert.equal(completions(t).length,0);
  });
  await test('완료 POST만 실패하면 차트를 유지하고 알림만 재시도',async()=>{
    const t=setup();t.setFailNotify(true);await t.window.initSevenChartUI();await t.flush();
    assert.equal(t.charts.size,2);assert.equal(completions(t).length,1);
    assert.match(status(t),/차트는 표시됐지만 완료 알림/);
    const getCount=t.calls.filter(c=>c.url==='/study/seven-day-report/41').length;
    const graph=t.charts.get('radarChart');t.setFailNotify(false);
    await t.window.studyState.refresh();await t.flush();
    assert.equal(completions(t).length,2);assert.equal(t.charts.get('radarChart'),graph);
    assert.equal(t.calls.filter(c=>c.url==='/study/seven-day-report/41').length,getCount);
    assert.equal(status(t),'');
  });
  await test('캐시 용량 부족이어도 표시·완료 판단은 실제 그래프 기준',async()=>{
    const t=setup();t.setStorageFull(true);await t.window.initSevenChartUI();await t.flush();
    assert.equal(t.charts.size,2);assert.equal(completions(t).length,1);
  });
  await test('표시 후 계정이 바뀌면 이전 결과 완료 재전송 차단',async()=>{
    const t=setup();await t.window.initSevenChartUI();await t.flush();const before=completions(t).length;
    t.storage.set('access_token','other-token');t.storage.set('user_id','2');
    assert.equal(await t.context.notifyChartLoadingComplete(41),false);
    assert.equal(completions(t).length,before);
  });
  await test('완료된 화면을 떠나면 이전 캔버스로 완료 재전송 차단',async()=>{
    const t=setup();await t.window.initSevenChartUI();await t.flush();const before=completions(t).length;
    t.buildDom();assert.equal(await t.context.notifyChartLoadingComplete(41),false);
    assert.equal(completions(t).length,before);
  });
  console.log(`Bundle 4 frontend: ${count} scenarios passed`);
})().catch(error=>{console.error(error);process.exitCode=1;});
