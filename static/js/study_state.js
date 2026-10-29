// 서버 저장 상태를 기준으로 복원한다. 알림·캐시는 상태 갱신을 돕는 수단이다.
(() => {
  const daily = new Set(['diary_available', 'diary_unavailable', 'diary_reset',
    'encourage_available', 'encourage_unavailable']);
  const weekly = new Set(['seven_day_report', 'chart_loading_complete']);
  const pairs = {diary_available:'diary_unavailable', diary_unavailable:'diary_available',
    encourage_available:'encourage_unavailable', encourage_unavailable:'encourage_available',
    seven_day_report:'chart_loading_complete', chart_loading_complete:'seven_day_report'};
  const get = key => localStorage.getItem(key);
  const owner = () => String(get('user_id') || '');
  const kstDate = value => new Intl.DateTimeFormat('en-CA', {
    timeZone:'Asia/Seoul', year:'numeric', month:'2-digit', day:'2-digit'
  }).format(new Date(value));
  let clockOffset = 0, snapshot = null, inFlight = null, refreshAgain = false;
  const today = () => kstDate(Date.now() + clockOffset);
  const emit = (type, detail) => document.dispatchEvent(new CustomEvent(type, {detail}));
  const isCurrent = (token, uid) => get('access_token') === token && owner() === uid;

  window.createNotificationManager = function() {
    return {
      storedNotifications: {},
      persist() {
        try {
          localStorage.setItem('notifications', JSON.stringify(this.storedNotifications));
          localStorage.setItem('notifications_owner', owner());
        } catch (_) { /* 저장 공간이 없어도 현재 화면 상태는 갱신한다. */ }
      },
      isFresh(data) {
        if (!daily.has(data.type)) return true;
        try {
          const date = data.date || data.server_date ||
            (data.timestamp ? kstDate(data.timestamp) : today());
          return date === today();
        } catch (_) { return false; }
      },
      initializeFromStorage() {
        try {
          const saved = get('notifications_owner') === owner() ? JSON.parse(get('notifications') || '{}') : {};
          this.storedNotifications = saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
          for (const [key, value] of Object.entries(this.storedNotifications)) {
            if (!value || !this.isFresh({...value, type:key})) delete this.storedNotifications[key];
          }
          // 구형 캐시에 반대 상태가 함께 있으면 수신 시각상 최신 한 개만 남긴다.
          for (const [a,b] of [['diary_available','diary_unavailable'],
            ['encourage_available','encourage_unavailable'], ['seven_day_report','chart_loading_complete']]) {
            if (this.storedNotifications[a] && this.storedNotifications[b]) {
              const aTime = this.storedNotifications[a].received_at || this.storedNotifications[a].timestamp || 0;
              const bTime = this.storedNotifications[b].received_at || this.storedNotifications[b].timestamp || 0;
              delete this.storedNotifications[aTime > bTime ? b : a];
            }
          }
        } catch (_) { this.storedNotifications = {}; }
        this.persist();
      },
      storeNotification(data) {
        if (!data || !this.isFresh(data)) return;
        if (weekly.has(data.type)) {
          const current = this.storedNotifications.seven_day_report || this.storedNotifications.chart_loading_complete;
          if (current && Number(data.analysis_id) < Number(current.analysis_id)) return;
        }
        const stateEvent = daily.has(data.type) || weekly.has(data.type);
        const existing = this.storedNotifications[data.type];
        if (!stateEvent && existing?.priority === 'high' && data.priority !== 'high') return;
        this.updateNotification(data.type, data);
        if (stateEvent) window.studyState.refresh(true);
      },
      updateNotification(key, data) {
        if (key === 'diary_reset') {
          for (const type of daily) delete this.storedNotifications[type];
        }
        if (pairs[key]) delete this.storedNotifications[pairs[key]];
        this.storedNotifications[key] = {...data, date: daily.has(key) ? today() : data.date,
          received_at:Date.now(), isActive:true};
        this.persist();
        if (key === 'final_report') {
          localStorage.setItem('final_report_data', JSON.stringify({report_id:data.report_id, timestamp:data.timestamp}));
        }
        // 저장과 전달 타입을 일치시킨다. 불가/자정 초기화도 즉시 전달한다.
        if (daily.has(key) || weekly.has(key) || key === 'final_report') this.dispatchToAllComponents(data);
      },
      dispatchToAllComponents(data) { emit(data.type, data); },
      clearNotification(type) { delete this.storedNotifications[type]; this.persist(); },
      restoreNotifications(page) {
        if (page === 'study') {
          for (const item of Object.values(this.storedNotifications)) {
            if ((daily.has(item.type) || weekly.has(item.type)) && item.isActive && this.isFresh(item)) {
              // reset을 화면 진입마다 재실행하지 않는다.
              if (item.type !== 'diary_reset') this.dispatchToAllComponents(item);
            }
          }
          return window.studyState.refresh();
        }
        if (page === 'constellation') {
          const report = this.storedNotifications.final_report;
          let cached = null;
          try { cached = JSON.parse(get('final_report_data') || 'null'); } catch (_) {}
          if (report?.isActive && (!cached || cached.report_id !== report.report_id)) this.dispatchToAllComponents(report);
        }
      },
      checkNotificationStatus(page) {
        const names = page === 'study' ? ['diary_available','diary_unavailable'] :
          page === 'study_encourage' ? ['encourage_available','encourage_unavailable'] : ['seven_day_report'];
        const active = name => Boolean(this.storedNotifications[name]?.isActive && this.isFresh(this.storedNotifications[name]));
        return {hasAvailable:active(names[0]), hasEncourage:active(names[0]),
          hasUnavailable:active(names[1]), hasAnyNotification:names.some(active)};
      },
      applyServerState(data) {
        // 오래된 날짜/우선순위의 알림이 서버의 현재 결과를 덮어쓰지 않게 한다.
        for (const type of daily) delete this.storedNotifications[type];
        const base = {date:data.server_date, restored:true};
        this.updateNotification(data.diary.available ? 'diary_available' : 'diary_unavailable', {
          ...base, type:data.diary.available ? 'diary_available' : 'diary_unavailable',
          reason:data.diary.state === 'saved' ? '오늘 이미 AI로 생성한 일기가 있습니다.' :
            data.diary.available ? '일기 생성이 가능합니다.' : '오늘의 대화가 더 필요합니다.'});
        const letter = data.encouragement;
        const read = get('encourage_owner') === String(data.user_id) && get('encourage_result_id') === String(letter.id);
        const type = letter.state === 'ready' && !read ? 'encourage_available' : 'encourage_unavailable';
        this.updateNotification(type, {...base, type, result_id:letter.id});
        if (data.weekly.state === 'ready') {
          this.updateNotification('seven_day_report', {type:'seven_day_report',
            analysis_id:data.weekly.analysis_id, restored:true});
        } else {
          delete this.storedNotifications.seven_day_report;
          delete this.storedNotifications.chart_loading_complete;
          this.persist();
        }
      }
    };
  };

  window.studyState = {
    today,
    current() { return snapshot && String(snapshot.user_id) === owner() ? snapshot : null; },
    refresh(force = false) {
      if (!get('access_token')) return Promise.resolve(null);
      if (inFlight) { refreshAgain ||= force; return inFlight; }
      const token = get('access_token'), uid = owner();
      const request = (async () => {
        try {
          const response = await fetch('/study/status', {headers:{Authorization:`Bearer ${token}`}, cache:'no-store'});
          if (!response.ok) throw new Error('status_unavailable');
          const data = await response.json();
          if (!isCurrent(token, uid) || String(data.user_id) !== uid) return null;
          clockOffset = Date.parse(data.server_now) - Date.now();
          if (!Number.isFinite(clockOffset)) clockOffset = 0;
          snapshot = data;
          window.globalNotificationManager?.applyServerState(data);
          emit('study_state_updated', data);
          return data;
        } catch (_) {
          if (isCurrent(token, uid)) emit('study_state_error', {});
          return null;
        }
      })();
      inFlight = request;
      request.finally(() => {
        inFlight = null;
        if (refreshAgain) { refreshAgain = false; this.refresh(); }
      });
      return request;
    }
  };
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') window.studyState.refresh();
  });
  window.addEventListener('focus', () => window.studyState.refresh());
  setInterval(() => {
    if (snapshot && snapshot.server_date !== today()) window.studyState.refresh();
  }, 30000);
})();
