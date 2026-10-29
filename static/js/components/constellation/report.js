// constellation/report.js - 성격 리포트 관리

// 서버 API 호출 - 성격 리포트 데이터 가져오기
async function fetchPersonalityReportData(reportId) {
  try {

    const response = await fetch(`/personality-report/${reportId}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
        'Content-Type': 'application/json'
      }
    });

    if (response.ok) {
      const data = await response.json();

      // 로컬스토리지에 저장
      localStorage.setItem('personality_report_data', JSON.stringify(data));

      // 리포트 렌더링
      renderPersonalityReport(data);
    } else {
    }
  } catch (error) {
  }
}

// 리포트 렌더링 함수
function renderPersonalityReport(data) {
  const fields = [
    ['top-box', '정서적 패턴', data.emotional_pattern],
    ['middle-box', '성향', data.personality_tendency],
    ['bottom-box', '무의식적 통찰', data.unconscious_insight]
  ];
  for (const [boxClass, title, value] of fields) {
    const box = document.querySelector(`.constellation-report-box.${boxClass}`);
    if (!box) continue;
    const content = document.createElement('div');
    content.className = 'report-content';
    const heading = document.createElement('h3');
    heading.textContent = title;
    const paragraph = document.createElement('p');
    paragraph.textContent = typeof value === 'string' ? value : '';
    paragraph.style.whiteSpace = 'pre-wrap';
    content.append(heading, paragraph);
    box.replaceChildren(content);
  }
}

// 전역 리스너 등록 (한 번만)
function bindConstellationListenersOnce() {
  if (window.__constellationListenersBound) return;
  window.__constellationListenersBound = true;


  // final_report 알림 리스너
  document.addEventListener('final_report', function(event) {
    const data = event.detail;

    // 서버에서 데이터 가져오기
    fetchPersonalityReportData(data.report_id);
  });
}

// 초기화 함수 - 탭 진입 시 호출
window.initConstellationUI = function() {
  bindConstellationListenersOnce();  // 리스너 보장


  // 기존 데이터가 있으면 리포트 렌더링
  const existingData = localStorage.getItem('personality_report_data');
  if (existingData) {
    try {
      const data = JSON.parse(existingData);
      renderPersonalityReport(data);
    } catch (error) {
    }
  } else {
    // 기존 데이터가 없으면 로딩 상태 유지
    // HTML의 기본 로딩 메시지가 그대로 표시됨
  }

  // WebSocket 알림 상태 복원
  if (window.globalNotificationManager) {
    window.globalNotificationManager.restoreNotifications('constellation');
  }

};
