document.addEventListener('DOMContentLoaded', function() {
  // WebSocket 연결 관리
  let ws = null;
  let userId = null;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 10;
  const reconnectDelay = 3000; // 3초

  // 사용자 ID 가져오기 (localStorage에서)
  function getCurrentUserId() {
    const accessToken = localStorage.getItem('access_token');
    if (!accessToken) {
      console.error('❌ access_token이 없습니다');
      return null;
    }

    try {
      // JWT 토큰에서 user_id 추출
      const encoded = accessToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
      const payload = JSON.parse(atob(encoded.padEnd(Math.ceil(encoded.length / 4) * 4, '=')));
      if (!payload.exp || payload.exp * 1000 <= Date.now()) return null;
      console.log('✅ 사용자 ID 추출:', payload.user_id);
      return payload.user_id;
    } catch (error) {
      console.error('❌ 토큰 파싱 실패:', error);
      return null;
    }
  }

  // WebSocket 연결 상태 확인
  function isWebSocketConnected() {
    return ws && ws.readyState === WebSocket.OPEN;
  }

  // WebSocket 연결
  function connectWebSocket() {
    userId = getCurrentUserId();
    if (!userId) {
      console.error('❌ 사용자 ID를 가져올 수 없어 WebSocket 연결을 건너뜁니다');
      return;
    }

    // 기존 연결이 있으면 닫기
    if (ws) {
      ws.close();
    }

    console.log(`🔗 WebSocket 연결 시도: user_id=${userId}`);
    const socketProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${socketProtocol}//${window.location.host}/ws/${userId}`);

    ws.onopen = function() {
      ws.send(JSON.stringify({
        type: 'authenticate',
        token: localStorage.getItem('access_token')
      }));
      console.log('✅ WebSocket 연결됨');
      reconnectAttempts = 0; // 연결 성공 시 재시도 횟수 초기화
      window.studyState.refresh(true);
    };

    ws.onmessage = function(event) {
      const data = JSON.parse(event.data);
      if (data.type === 'pong') return;
      if (['report', 'final_report', 'plant_generation'].includes(data.type)) return;
      // 전역 알림 관리자에 저장 (우선순위 처리 포함)
      window.globalNotificationManager.storeNotification(data);
    };

    ws.onclose = function(event) {
      console.log('❌ WebSocket 연결 해제됨:', event.code, event.reason);

      // 정상적인 종료가 아닌 경우에만 재연결 시도
      if (event.code !== 1000 && event.code !== 1008 && reconnectAttempts < maxReconnectAttempts) {
        console.log(`🔄 재연결 시도 ${reconnectAttempts + 1}/${maxReconnectAttempts}`);
        setTimeout(connectWebSocket, reconnectDelay);
        reconnectAttempts++;
      } else if (reconnectAttempts >= maxReconnectAttempts) {
        console.error('❌ 최대 재연결 시도 횟수 초과');
      }
    };

    ws.onerror = function(error) {
      console.error('❌ WebSocket 에러:', error);
    };
  }

  // 전역 알림 관리자 초기화
  window.globalNotificationManager = window.createNotificationManager();

  // final_report 알림 리스너 등록 (한 번만)
  function bindFinalReportListenerOnce() {
    if (!window.mvpFeatures?.upperReports) return;
    if (window.__finalReportListenerBound) return;
    window.__finalReportListenerBound = true;

    console.log('📋 final_report 리스너 등록됨');

    document.addEventListener('final_report', function(event) {
      const data = event.detail;

      if (data.type === 'final_report') {
        console.log('📋 final_report 알림 수신:', data);

        // 1. 현재 활성화된 메인 탭의 첫 번째 서브탭(알림)에 "1" 표시
        const activeMainTab = document.querySelector('.tab.active');
        if (activeMainTab) {
          // 서브탭 컨테이너에서 첫 번째 서브탭(알림) 찾기
          const subTabsContainer = document.querySelector('.sub-tabs');
          if (subTabsContainer) {
            const firstSubTab = subTabsContainer.querySelector('.sub-tab:first-child');

            if (firstSubTab) {
              // 기존 알림 숫자 제거
              const existingBadge = firstSubTab.querySelector('.notification-badge');
              if (existingBadge) {
                existingBadge.remove();
              }

              // 새 알림 배지 추가
              const badge = document.createElement('span');
              badge.className = 'notification-badge';
              badge.textContent = '1';
              badge.style.cssText = `
                background: #ff4444;
                color: white;
                border-radius: 50%;
                padding: 2px 6px;
                font-size: 12px;
                margin-left: 5px;
                display: inline-block;
                min-width: 18px;
                text-align: center;
                animation: pulse 1s infinite;
              `;
              firstSubTab.appendChild(badge);
            }
          }
        }

      // 2. 팝업 띄우기 (showConfirm 사용)
      if (window.popupManager) {
        window.popupManager.showConfirm(
          '분석리포트가 완성되었습니다. 확인하시겠습니까?',
          '분석 리포트 완성',
          function() {
            // 확인 버튼 클릭 시 constellation 페이지로 전환
            const constellationTab = document.querySelector('[data-tab="constellation"]');
            if (constellationTab) {
              constellationTab.click();
            }
          },
          function() {
            // 취소 버튼 클릭 시 (아무것도 안함)
            console.log('사용자가 취소를 선택함');
          }
        );
      } else {
        // popupManager가 없으면 기본 confirm 사용
        const confirmed = confirm('분석리포트가 완성되었습니다. 확인하시겠습니까?');
        if (confirmed) {
          const constellationTab = document.querySelector('[data-tab="constellation"]');
          if (constellationTab) {
            constellationTab.click();
          }
        }
      }
    }
  });
  }

  // 전역 알림 관리자 초기화 (localStorage에서 복원)
  window.globalNotificationManager.initializeFromStorage();
  window.studyState.refresh();

  // final_report 리스너 한 번만 등록
  bindFinalReportListenerOnce();

  // WebSocket 연결 시작
  connectWebSocket();

  // X 버튼 동작
  const closeBtn = document.getElementById('close-dashboard-btn');
  if (closeBtn) {
    closeBtn.addEventListener('click', function() {
      document.querySelectorAll('.main-tab').forEach(tab => tab.classList.remove('active'));
      document.querySelectorAll('.sub-tab').forEach(tab => tab.classList.remove('active'));
      window.location.href = '/';
    });
  }

  // 동적 영역 지정
  const mainTabs = document.querySelectorAll('.main-tab');
  const mainContent = document.getElementById('main-content');
  const subTabs = document.querySelector('.sub-tabs');

  // 공간 탭 콘텐츠 로드 함수
  function loadSpaceSection() {
    fetch('/templates/components/space/section.html')
      .then(res => res.text())
      .then(html => {
        mainContent.innerHTML = html;
        import('/static/js/components/space/section.js').then(() => {
          if (window.initSpaceSection) {
            window.initSpaceSection();
          }
        });
      });
  }

  // 서재 탭 콘텐츠 로드 함수
  function loadStudySection() {
    fetch('/templates/components/study/section.html')
      .then(res => res.text())
      .then(html => {
        mainContent.innerHTML = html;

        // 모듈 준비 뒤 상태를 복원한다. 타이머 속도에 의존하지 않는다.
        import('/static/js/components/study/section.js').then(() => {
          window.globalNotificationManager.restoreNotifications('study');
        });
      });

    // CSS 동적 로드 (이미 링크되어 있지 않으면)
    if (!document.querySelector('link[href="/static/css/components/study/section.css"]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/static/css/components/study/section.css';
      document.head.appendChild(link);
    }
  }

  // 채팅하기 탭 콘텐츠 로드 함수
  function loadChattingSection() {
    fetch('/templates/components/chatting/section.html')
      .then(res => res.text())
      .then(html => {
        mainContent.innerHTML = html;
        import('/static/js/components/chatting/section.js?v=20261030-stream1').then(() => {
          if (window.initChattingSection) window.initChattingSection();
        });
      });
  }

  function showPreparing(name) {
    mainContent.replaceChildren();
    const notice = document.createElement('p');
    notice.textContent = `${name} 기능은 준비 중입니다.`;
    notice.style.cssText = 'padding:40px;text-align:center;';
    mainContent.appendChild(notice);
  }

  // 텃밭 탭 콘텐츠 로드 함수
  function loadGardenSection() {
    if (!window.mvpFeatures?.garden) return showPreparing('텃밭');
    fetch('/templates/components/garden/section.html')
      .then(res => res.text())
      .then(html => {
        mainContent.innerHTML = html;
        import('/static/js/components/garden/section.js');
      });
  }

  // 별자리(리포트) 탭 콘텐츠 로드 함수
  function loadConstellationSection() {
    if (!window.mvpFeatures?.upperReports) return showPreparing('리포트');
    fetch('/templates/components/constellation/report.html')
      .then(response => response.text())
      .then(html => {
        mainContent.innerHTML = html;

        // JS 모듈 로드
        console.log('constellation/report.js 로드 시작');
        import('/static/js/components/constellation/report.js').then(() => {
          console.log('constellation/report.js 로드 완료');

          // 초기화 함수 호출
          if (window.initConstellationUI) {
            console.log('initConstellationUI 함수 호출');
            window.initConstellationUI();
          } else {
            console.error('initConstellationUI 함수를 찾을 수 없습니다.');
          }
        }).catch(err => {
          console.error('constellation/report.js 로드 실패:', err);
        });
      })
      .catch(error => {
        console.error('Constellation report 로드 실패:', error);
        mainContent.innerHTML = '<div style="padding: 20px; text-align: center;"><p>리포트 기능이 준비 중입니다.</p></div>';
      });
  }

  // 서브탭 로드 함수
  function updateSubTabs(tab) {
    if (!subTabs) return;
    if ((tab === 'garden' && !window.mvpFeatures?.garden) ||
        (tab === 'constellation' && !window.mvpFeatures?.upperReports)) {
      subTabs.replaceChildren();
      return;
    }
    if (tab === 'garden') {
      subTabs.innerHTML = `
        <div class="sub-tab">알림</div>
        <div class="sub-tab active">나의 텃밭</div>
        <div class="sub-tab">씨앗 심기</div>
        <div class="sub-tab">씨앗 가꾸기</div>
      `;
    } else if (tab === 'chatting') {
      subTabs.innerHTML = `
        <div class="sub-tab">알림</div>
        <div class="sub-tab active">대화하기</div>
        <div class="sub-tab">채팅목록</div>
      `;
    } else if (tab === 'study') {
      subTabs.innerHTML = `
        <div class="sub-tab">알림</div>
        <div class="sub-tab active">나의 서재</div>
        <div class="sub-tab">일기생성</div>
        <div class="sub-tab">일주일 차트</div>
        <div class="sub-tab">하루의 마무리</div>
      `;
    } else if (tab === 'constellation') {
      subTabs.innerHTML = `
        <div class="sub-tab">알림</div>
        <div class="sub-tab active">분석 리포트</div>
      `;

    } else {
      subTabs.innerHTML = `<div class="sub-tab">알림</div>`;
    }
  }

  // 항상 '공간' 탭이 기본 active + 콘텐츠 로드
  const requestedPanel = new URLSearchParams(window.location.search).get('panel');
  const directStudy = new URLSearchParams(window.location.search).get('tab') === 'study' && ['weekly','encourage'].includes(requestedPanel);
  if (mainTabs.length > 0 && !directStudy) {
    mainTabs.forEach(tab => tab.classList.remove('active'));
    const spaceTab = document.querySelector('.main-tab[data-tab="space"]');
    if (spaceTab) spaceTab.classList.add('active');
    loadSpaceSection();
    updateSubTabs('space');
  }

  // 탭 클릭 시 active 전환 및 콘텐츠/서브탭 변경
  mainTabs.forEach(tab => {
    tab.addEventListener('click', function() {
      mainTabs.forEach(t => t.classList.remove('active'));
      this.classList.add('active');
      if (this.dataset.tab === 'space') {
        loadSpaceSection();
        updateSubTabs('space');
      } else if (this.dataset.tab === 'study') {
        loadStudySection();
        updateSubTabs('study');
      } else if (this.dataset.tab === 'chatting') {
        loadChattingSection();
        updateSubTabs('chatting');
      } else if (this.dataset.tab === 'garden') {
        loadGardenSection();
        updateSubTabs('garden');
      } else if (this.dataset.tab === 'constellation') {
        loadConstellationSection();
        updateSubTabs('constellation');
      } else {
        mainContent.innerHTML = '';
        updateSubTabs();
      }
      // 서브탭 active 해제는 updateSubTabs에서 처리됨
    });
  });

  // 서브탭 클릭 시 active 처리 및 콘텐츠 전환
  document.addEventListener('click', function(e) {
    if (e.target.classList.contains('sub-tab')) {
      const active = document.querySelector('.main-tab.active')?.dataset.tab;
      if ((active === 'garden' && !window.mvpFeatures?.garden) ||
          (active === 'constellation' && !window.mvpFeatures?.upperReports)) return;
      document.querySelectorAll('.sub-tab').forEach(tab => tab.classList.remove('active'));
      e.target.classList.add('active');

      // 씨앗 심기 클릭 시 콘텐츠 전환
      if (e.target.textContent.trim() === '씨앗 심기') {
        fetch('/templates/components/garden/sub_seed_made.html')
          .then(res => res.text())
          .then(html => {
            mainContent.innerHTML = html;
            import('/static/js/components/garden/sub_seed_made.js');
          });
        // CSS 동적 로드 (이미 링크되어 있지 않으면)
        if (!document.querySelector('link[href="/static/css/components/garden/sub_seed_made.css"]')) {
          const link = document.createElement('link');
          link.rel = 'stylesheet';
          link.href = '/static/css/components/garden/sub_seed_made.css';
          document.head.appendChild(link);
        }
      }

      // 대화하기 클릭 시 콘텐츠 전환
      if (e.target.textContent.trim() === '대화하기') {
        fetch('/templates/components/chatting/section.html')
          .then(res => res.text())
          .then(html => {
            mainContent.innerHTML = html;
            import('/static/js/components/chatting/section.js?v=20261030-stream1').then(() => {
              if (window.initChattingSection) window.initChattingSection();
            });
          });
      }

      // 채팅목록 클릭 시 콘텐츠 전환
      if (e.target.textContent.trim() === '채팅목록') {
        console.log('채팅목록 서브 탭 클릭됨');
        fetch('/templates/components/chatting/sub_chat_list.html')
          .then(res => {
            console.log('sub_chat_list.html 응답 상태:', res.status);
            return res.text();
          })
          .then(html => {
            console.log('sub_chat_list.html 로드됨');
            mainContent.innerHTML = html;
            console.log('sub_chat_list.js 로드 시작');
            import('/static/js/components/chatting/sub_chat_list.js').then(() => {
              console.log('sub_chat_list.js 로드 완료');
              // 초기화 함수 호출
              if (window.initChatList) {
                console.log('initChatList 함수 호출');
                window.initChatList();
              } else {
                console.error('initChatList 함수를 찾을 수 없습니다.');
              }
            }).catch(err => {
              console.error('sub_chat_list.js 로드 실패:', err);
            });
          })
          .catch(err => {
            console.error('sub_chat_list.html 로드 실패:', err);
          });
      }

      // 일주일 차트 클릭 시 콘텐츠 전환
      if (e.target.textContent.trim() === '일주일 차트') {
        switchToSevenChartTab();
      }

      // 나의 텃밭 클릭 시 콘텐츠 전환
      if (e.target.textContent.trim() === '나의 텃밭') {
        fetch('/templates/components/garden/section.html')
          .then(res => res.text())
          .then(html => {
            mainContent.innerHTML = html;
            import('/static/js/components/garden/section.js');
          });
      }

      // 나의 서재 클릭 시 콘텐츠 전환
      if (e.target.textContent.trim() === '나의 서재') {
        fetch('/templates/components/study/section.html')
          .then(res => res.text())
          .then(html => {
            mainContent.innerHTML = html;
            import('/static/js/components/study/section.js').then(() => {
              // WebSocket 알림 상태 복원
              console.log('📤 나의 서재 서브탭 - WebSocket 알림 상태 복원');
              window.globalNotificationManager.restoreNotifications('study');

              // 상태 체크 함수 호출
              if (window.checkStudyNotificationStatus) {
                window.checkStudyNotificationStatus();
              }
            });
          });
      }


      // 일기생성 클릭 시 콘텐츠 전환
      if (e.target.textContent.trim() === '일기생성') {
        switchToDiaryGenerateTab();
      }

      // 하루의 마무리 클릭 시 콘텐츠 전환
      if (e.target.textContent.trim() === '하루의 마무리') {
        switchToEncourageTab();
      }



    }
  });

  // 일기생성 서브탭 전환 함수
  function switchToDiaryGenerateTab() {
    console.log('일기생성 서브 탭 클릭됨');
    fetch('/templates/components/study/sub_diary_generate.html')
      .then(res => {
        console.log('sub_diary_generate.html 응답 상태:', res.status);
        return res.text();
      })
      .then(html => {
        console.log('sub_diary_generate.html 로드됨');
        mainContent.innerHTML = html;
        console.log('sub_diary_generate.js 로드 시작');
        import('/static/js/components/study/sub_diary_generate.js').then(() => {
          console.log('sub_diary_generate.js 로드 완료');

          // WebSocket 알림 상태 복원
          console.log('📤 일기생성 서브탭 - WebSocket 알림 상태 복원');
          window.globalNotificationManager.restoreNotifications('study');

          // 초기화 함수 호출
          if (window.initDiaryGeneration) {
            console.log('initDiaryGeneration 함수 호출');
            window.initDiaryGeneration();
          } else {
            console.error('initDiaryGeneration 함수를 찾을 수 없습니다.');
          }
        }).catch(err => {
          console.error('sub_diary_generate.js 로드 실패:', err);
        });
      })
      .catch(err => {
        console.error('sub_diary_generate.html 로드 실패:', err);
      });

    // CSS 동적 로드 (이미 링크되어 있지 않으면)
    if (!document.querySelector('link[href="/static/css/components/study/sub_diary_generate.css"]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/static/css/components/study/sub_diary_generate.css';
      document.head.appendChild(link);
    }
  }

  // 하루의 마무리 서브탭 전환 함수
  function switchToEncourageTab() {
    console.log('하루의 마무리 서브 탭 클릭됨');
    fetch('/templates/components/study/encourage.html')
      .then(res => {
        console.log('encourage.html 응답 상태:', res.status);
        return res.text();
      })
      .then(html => {
        console.log('encourage.html 로드됨');
        mainContent.innerHTML = html;

        // ✅ 1) 모듈 import
        import('/static/js/components/study/encourage.js')
          .then(() => {
            // ✅ 2) 리스너 보장 + 즉시 상태 동기화
            if (window.initEncourageUI) {
              window.initEncourageUI();
            }

            // ✅ 3) (리스너 준비된 상태에서) 복원 이벤트 전파
            console.log('📤 하루의 마무리 서브탭 - WebSocket 알림 상태 복원');
            window.globalNotificationManager.restoreNotifications('study');
          })
          .catch(err => {
            console.error('encourage.js 로드 실패:', err);
          });
      })
      .catch(err => {
        console.error('encourage.html 로드 실패:', err);
      });
  }

  // 일주일 차트 서브탭 전환 함수
  function switchToSevenChartTab() {
    console.log('일주일 차트 서브 탭 클릭됨');

    // HTML 로드
    fetch('/templates/components/study/seven_chart.html')
      .then(res => {
        console.log('seven_chart.html 응답 상태:', res.status);
        return res.text();
      })
      .then(html => {
        console.log('seven_chart.html 로드됨');
        mainContent.innerHTML = html;

        // JS 모듈 로드
        console.log('seven_chart.js 로드 시작');
        import('/static/js/components/study/seven_chart.js').then(() => {
          console.log('seven_chart.js 로드 완료');

          // 초기화 함수 호출
          if (window.initSevenChartUI) {
            console.log('initSevenChartUI 함수 호출');
            window.initSevenChartUI();
          } else {
            console.error('initSevenChartUI 함수를 찾을 수 없습니다.');
          }
        }).catch(err => {
          console.error('JS 모듈 로드 실패:', err);
        });

        console.log('일주일 차트 페이지 로드 완료');
      })
      .catch(err => {
        console.error('seven_chart.html 로드 실패:', err);
        mainContent.innerHTML = '<p>일주일 차트를 불러오는 중 오류가 발생했습니다.</p>';
      });
  }

  // diary_reset 이벤트 리스너 추가
  document.addEventListener('diary_reset', function(event) {
    const data = event.detail;
    console.log('🕛 diary_reset 이벤트 수신:', data);

    // 전역 알림 관리자에서 diary_unavailable 제거
    if (window.globalNotificationManager) {
      window.globalNotificationManager.clearNotification('diary_unavailable');
    }

    // 전역 상태 초기화
    window.diaryUnavailableReason = null;
        window.lastCheckedDate = new Date().toLocaleDateString('ko-KR');

    console.log('✅ 자정 리셋 완료 - diary_unavailable 상태 제거');
  });

  // 전역으로 노출
  window.switchToDiaryGenerateTab = switchToDiaryGenerateTab;
  window.switchToEncourageTab = switchToEncourageTab;
  window.switchToSevenChartTab = switchToSevenChartTab;
  // 새 홈의 서재 메뉴에서도 기존 열람 기능으로 바로 들어간다.
  if (window.location?.search && new URLSearchParams(window.location.search).get('tab') === 'study') {
    mainTabs.forEach(tab => { if (tab.dataset.tab !== 'study') tab.hidden = true; });
    const back = document.createElement('a');
    back.href = '/library'; back.textContent = '서재로 돌아가기'; back.className = 'main-tab';
    document.querySelector('.main-tabs')?.prepend(back);
    if (directStudy) {
      mainTabs.forEach(tab => tab.classList.toggle('active',tab.dataset.tab === 'study'));
      updateSubTabs('study');
      for (const tab of subTabs?.querySelectorAll('.sub-tab') || []) tab.classList.toggle('active',tab.textContent === (requestedPanel === 'weekly' ? '일주일 차트' : '하루의 마무리'));
      if (requestedPanel === 'weekly') switchToSevenChartTab(); else switchToEncourageTab();
    } else document.querySelector('.main-tab[data-tab="study"]')?.click();
  }
});
