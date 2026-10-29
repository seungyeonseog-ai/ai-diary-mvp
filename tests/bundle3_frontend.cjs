// 실제 상태 관리자·응원·차트 JS. HTTP/DOM/Chart 대체, 외부 호출 없음.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
process.env.TZ = 'America/Los_Angeles';
const root = path.join(__dirname, '..');
const sources = ['static/js/study_state.js', 'static/js/components/study/encourage.js',
  'static/js/components/study/seven_chart.js'].map(p => fs.readFileSync(path.join(root,p),'utf8'));
const day = '2026-10-29';
const letterText = '오늘도 수고했어요.\n<img src=x onerror=alert(1)>';
const state = () => ({user_id:1, server_date:day, server_now:day+'T12:00:00+09:00',
  diary:{available:false,state:'insufficient'}, encouragement:{state:'ready',id:9,date:day},
  weekly:{state:'ready',analysis_id:41}});
const weeklyData = () => ({weekly_analysis:{id:41,start_date:'10-20',end_date:'10-26',
  emotion_trend:{trend:'합성',dominant_emotion:'기쁨',recommendation:'쉬기'},
  keyword_patterns:{main_themes:['성장'],insights:'합성'}, overall_assessment:'합성'},
  diary_analyses:Array.from({length:7},(_,i)=>({id:i+1,date_str:`2026-10-${20+i}`,
    emotions:['기쁨'],scores:[0.5],keywords:['합성'],keyword_descriptions:['합성'],summary:'합성'}))});

function setup() {
  const storage = new Map([['access_token','synthetic-token'],['user_id','1']]);
  const ids = new Map(), listeners = new Map(), windowListeners = new Map(), calls = [], events = [], timers = [];
  const charts = new Map();
  class Element {
    constructor(tag='div') {this.tagName=tag;this.children=[];this.style={};this.dataset={};this.attrs={};this._text='';
      const classes = new Set();
      this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),
        toggle:(x,on)=>on ? classes.add(x):classes.delete(x)};
    }
    set id(value) {this._id=value;ids.set(value,this);} get id() {return this._id;}
    set textContent(value) {this._text=String(value??'');this.children=[];}
    get textContent() {return this._text+this.children.map(c=>c.textContent).join('');}
    set innerHTML(value) {this.textContent=value;}
    appendChild(child) {this.children.push(child);return child;}
    prepend(child) {this.children.unshift(child);}
    replaceChildren(...nodes) {this._text='';this.children=nodes;}
    appendData(text) {this._text+=text;}
    setAttribute(k,v) {this.attrs[k]=v;}
    getAttribute(k) {return this.attrs[k];}
    querySelector() {return null;}
  }
  function buildDom() {
    ids.clear();
    for (const id of ['encourage-btn','encourage-message','emotionTrendChart','radarChart',
      'emotionTrendText','comprehensiveAssessment','mainTrend','dominantEmotion','recommendations',
      'weeklyAssessment','mainThemesList','insightsContainer']) {const e=new Element();e.id=id;}
    const chartRoot = new Element(); chartRoot.id='chart-root';
  }
  buildDom();
  let remote=state(), failStatus=false, failLetter=false, failWeekly=false, holdStatus=null;
  class FakeChart {
    constructor(element, config) {this.config=config;this.element=element;charts.set(element.id,this);}
    destroy() {charts.delete(this.element.id);}
    static getChart(id) {return charts.get(id);}
  }
  const document = {visibilityState:'visible',
    getElementById:id=>ids.get(id)||null, createElement:tag=>new Element(tag),
    createTextNode:text=>{const e=new Element('#text');e.textContent=text;return e;},
    querySelector:selector=>selector==='.seven-chart-container' ? ids.get('chart-root'):null,
    addEventListener:(type,callback)=>{if(!listeners.has(type))listeners.set(type,[]);listeners.get(type).push(callback);},
    dispatchEvent:event=>{events.push(event);for(const callback of listeners.get(event.type)||[])callback(event);}
  };
  const window={addEventListener:(type,callback)=>windowListeners.set(type,callback)};
  const context=vm.createContext({window,document,Intl,Date,Chart:FakeChart,Promise,
    console:{log(){},error(){},warn(){}},
    CustomEvent:class{constructor(type,opts){this.type=type;this.detail=opts.detail;}},
    localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,String(v)),removeItem:k=>storage.delete(k)},
    setInterval:fn=>timers.push(fn),setTimeout:fn=>fn(),
    fetch:async(url,opts)=>{
      calls.push({url,opts});
      if(url==='/study/status') {
        if(holdStatus) return holdStatus;
        return {ok:!failStatus,status:failStatus?503:200,json:async()=>structuredClone(remote)};
      }
      if(url==='/study/encourage') return {ok:!failLetter,status:failLetter?503:200,json:async()=>({
        id:remote.encouragement.id,date:remote.server_date,server_date:remote.server_date,
        timestamp:remote.server_date+'T12:00:00+09:00',encourage_content:letterText})};
      if(url.startsWith('/study/seven-day-report/')) return {ok:!failWeekly,status:failWeekly?409:200,json:async()=>{
        const data=weeklyData();data.weekly_analysis.id=Number(url.split('/').pop());return data;}};
      if(url==='/study/chart-loading-complete') return {ok:true};
      throw new Error('Unexpected endpoint '+url);
    }
  });
  for(const source of sources) vm.runInContext(source,context);
  window.globalNotificationManager=window.createNotificationManager();
  const manager=window.globalNotificationManager;
  const flush=async()=>{for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));};
  return {context,window,manager,storage,ids,calls,events,timers,charts,document,buildDom,flush,
    setRemote:value=>remote=value, setFailStatus:value=>failStatus=value,
    setFailLetter:value=>failLetter=value,setFailWeekly:value=>failWeekly=value,setHold:value=>holdStatus=value};
}

(async()=>{
  let count=0;
  async function test(name,run) {await run();count++;console.log('PASS '+name);}
  await test('캐시·알림 없이 저장된 응원/주간 복원',async()=>{
    const t=setup();await Promise.all([t.window.initEncourageUI(),t.window.initSevenChartUI()]);await t.flush();
    assert.equal(t.ids.get('encourage-message').textContent,letterText);
    assert.equal(t.charts.size,2);
    assert.equal(t.calls.filter(c=>c.url==='/study/encourage').length,1);
    assert.equal(t.calls.filter(c=>c.url==='/study/seven-day-report/41').length,1);
    assert.ok(!t.ids.get('encourage-message').dataset.resultKey.includes('synthetic-token'));
  });
  await test('오래된 응원 캐시를 서버 응답 전에 표시하지 않음',async()=>{
    const t=setup();t.storage.set('encourage_content','OLD_PRIVATE_LETTER');
    t.storage.set('encourage_timestamp','2020-01-01T00:00:00+09:00');
    let release;t.setHold(new Promise(resolve=>release=resolve));
    const pending=t.window.initEncourageUI();
    assert.ok(!t.ids.get('encourage-message').textContent.includes('OLD_PRIVATE'));
    release({ok:true,json:async()=>state()});await pending;await t.flush();
    assert.equal(t.ids.get('encourage-message').textContent,letterText);
  });
  await test('한국 날짜는 브라우저 미국 시간대와 무관',async()=>{
    const t=setup();await t.window.studyState.refresh();
    assert.equal(t.context.isToday('2026-10-28T16:00:00Z'),true);
    assert.equal(t.context.isToday('2026-10-28T14:00:00Z'),false);
  });
  await test('지난 날짜 응원 캐시 삭제',async()=>{
    const t=setup();await t.window.studyState.refresh();
    t.storage.set('encourage_content','old');t.storage.set('encourage_timestamp','2020-01-01T00:00:00Z');
    t.context.renderEncourageFromLocalStorage();assert.equal(t.storage.has('encourage_content'),false);
    assert.equal(t.ids.get('encourage-message').textContent,'');
  });
  await test('자정 다음 날에는 이전 편지·가능 상태 제거',async()=>{
    const t=setup();await t.window.initEncourageUI();await t.flush();
    const next=state();next.server_date='2026-10-30';next.server_now='2026-10-30T00:00:01+09:00';
    next.encouragement={state:'insufficient',id:null,date:null};next.diary={state:'insufficient',available:false};
    t.setRemote(next);await t.window.studyState.refresh();await t.flush();
    assert.ok(!t.ids.get('encourage-message').textContent.includes(letterText));
    assert.equal(t.storage.has('encourage_content'),false);
    assert.equal(Boolean(t.manager.storedNotifications.encourage_available),false);
  });
  await test('응원 불가·자정 초기화 즉시 전달',async()=>{
    const t=setup();await t.window.studyState.refresh();t.events.length=0;
    t.manager.storeNotification({type:'encourage_unavailable',date:day});
    assert.equal(t.events[0].type,'encourage_unavailable');
    t.events.length=0;t.manager.storeNotification({type:'diary_reset',date:day});
    assert.equal(t.events[0].type,'diary_reset');await t.flush();
  });
  await test('반대 알림은 하나만 남고 높은 과거 우선순위가 새 상태를 막지 않음',async()=>{
    const t=setup();await t.window.studyState.refresh();
    t.manager.storeNotification({type:'encourage_unavailable',priority:'high',date:day});
    t.manager.storeNotification({type:'encourage_available',priority:'normal',date:day});
    assert.equal(Boolean(t.manager.storedNotifications.encourage_unavailable),false);
    assert.ok(t.manager.storedNotifications.encourage_available);await t.flush();
  });
  await test('늦게 온 지난 날짜 알림 무시',async()=>{
    const t=setup();await t.window.studyState.refresh();const before=t.events.length;
    t.manager.storeNotification({type:'diary_reset',date:'2026-10-28'});
    assert.equal(t.events.length,before);
  });
  await test('손상된 알림 JSON으로 초기화가 중단되지 않음',async()=>{
    const t=setup();t.storage.set('notifications_owner','1');t.storage.set('notifications','broken');
    t.manager.initializeFromStorage();assert.deepEqual(Object.keys(t.manager.storedNotifications),[]);
  });
  await test('다른 계정의 알림 캐시 무시',async()=>{
    const t=setup();t.storage.set('notifications_owner','2');t.storage.set('notifications',JSON.stringify({diary_available:{type:'diary_available',date:day}}));
    t.manager.initializeFromStorage();assert.equal(Object.keys(t.manager.storedNotifications).length,0);
  });
  await test('과거 주간 캐시 ID보다 서버 최신 ID 사용',async()=>{
    const t=setup();t.storage.set('seven_day_report_data',JSON.stringify({analysis_id:999}));
    await t.window.initSevenChartUI();await t.flush();
    assert.equal(t.calls.some(c=>c.url.includes('/999')),false);
    assert.equal(JSON.parse(t.storage.get('seven_day_report_data')).analysis_id,41);
  });
  await test('늦게 온 오래된 차트 완료는 최신 결과 상태를 덮지 않음',async()=>{
    const t=setup();await t.window.studyState.refresh();
    t.manager.storeNotification({type:'chart_loading_complete',analysis_id:30});
    assert.equal(t.manager.storedNotifications.seven_day_report.analysis_id,41);
  });
  await test('상태 조회 실패는 오류와 재시도 표시',async()=>{
    const t=setup();t.setFailStatus(true);
    await Promise.all([t.window.initEncourageUI(),t.window.initSevenChartUI()]);await t.flush();
    assert.equal(t.ids.get('encourage-btn').dataset.state,'error');
    assert.ok(t.ids.get('chart-restore-status').textContent.includes('다시 불러오기'));
    t.setFailStatus(false);await t.window.studyState.refresh();await t.flush();
    assert.equal(t.ids.get('encourage-message').textContent,letterText);
  });
  await test('응원 조회 장애 후 재시도',async()=>{
    const t=setup();t.setFailLetter(true);await t.window.initEncourageUI();await t.flush();
    assert.equal(t.ids.get('encourage-btn').dataset.state,'error');
    t.setFailLetter(false);await t.window.handleEncourageClick();await t.flush();
    assert.equal(t.ids.get('encourage-message').textContent,letterText);
  });
  await test('주간 409 조회 오류 후 재시도',async()=>{
    const t=setup();t.setFailWeekly(true);await t.window.initSevenChartUI();await t.flush();
    assert.ok(t.ids.get('chart-restore-status').textContent.includes('불러오지 못했습니다'));
    t.setFailWeekly(false);await t.window.studyState.refresh();await t.flush();
    assert.equal(t.charts.size,2);
  });
  await test('조회 중 계정 변경 시 이전 응답 차단',async()=>{
    const t=setup();let release;t.setHold(new Promise(resolve=>release=resolve));
    const pending=t.window.initEncourageUI();t.storage.set('access_token','other-token');t.storage.set('user_id','2');
    release({ok:true,json:async()=>state()});await pending;await t.flush();
    assert.ok(!t.ids.get('encourage-message').textContent.includes(letterText));
    assert.equal(t.storage.has('encourage_content'),false);
  });
  await test('화면 재진입 후 저장 결과 재열람',async()=>{
    const t=setup();await Promise.all([t.window.initEncourageUI(),t.window.initSevenChartUI()]);await t.flush();
    t.buildDom();await Promise.all([t.window.initEncourageUI(),t.window.initSevenChartUI()]);await t.flush();
    assert.equal(t.ids.get('encourage-message').textContent,letterText);
    assert.equal(t.calls.filter(c=>c.url==='/study/seven-day-report/41').length,2);
  });
  await test('생성 대기·자료 부족은 캐시 대신 상태 안내',async()=>{
    const t=setup();const data=state();data.encouragement={state:'pending',id:null,date:null};
    data.weekly={state:'insufficient',analysis_id:null};t.setRemote(data);
    await Promise.all([t.window.initEncourageUI(),t.window.initSevenChartUI()]);await t.flush();
    assert.ok(t.ids.get('encourage-message').textContent.includes('준비하고'));
    assert.ok(t.ids.get('chart-restore-status').textContent.includes('부족합니다'));
    assert.equal(t.calls.some(c=>c.url==='/study/encourage'),false);
  });
  await test('날짜 없는 오래된 알림도 최종 상태는 서버와 일치',async()=>{
    const t=setup();const data=state();data.encouragement={state:'insufficient',id:null,date:null};
    t.setRemote(data);await t.window.studyState.refresh();
    t.manager.storeNotification({type:'encourage_available'});await t.flush();
    assert.equal(Boolean(t.manager.storedNotifications.encourage_available),false);
    assert.ok(t.manager.storedNotifications.encourage_unavailable);
  });
  await test('화면 복귀 시 놓친 결과를 다시 조회',async()=>{
    const t=setup();const data=state();data.encouragement={state:'pending',id:null,date:null};
    t.setRemote(data);await t.window.initEncourageUI();
    t.setRemote(state());t.document.dispatchEvent({type:'visibilitychange'});await t.flush();
    assert.equal(t.ids.get('encourage-message').textContent,letterText);
  });
  await test('상태 조회 중 도착한 알림은 후속 조회로 최신 결과 확인',async()=>{
    const t=setup();let release;t.setHold(new Promise(resolve=>release=resolve));
    const pending=t.window.initSevenChartUI();
    t.manager.storeNotification({type:'seven_day_report',analysis_id:42});
    const newer=state();newer.weekly.analysis_id=42;t.setRemote(newer);t.setHold(null);
    release({ok:true,json:async()=>state()});await pending;await t.flush();
    assert.equal(t.window.studyState.current().weekly.analysis_id,42);
    assert.equal(JSON.parse(t.storage.get('seven_day_report_data')).analysis_id,42);
  });
  console.log(`Bundle 3 frontend: ${count} scenarios passed`);
})().catch(error=>{console.error(error);process.exitCode=1;});
