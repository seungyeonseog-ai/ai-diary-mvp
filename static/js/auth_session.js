// 보호 API의 인증 실패를 공통 처리한다. 토큰 원문은 로그에 남기지 않는다.
(() => {
  if (window.__authSessionInstalled) return;
  window.__authSessionInstalled = true;
  const originalFetch = window.fetch.bind(window);
  let redirecting = false;

  function requireLogin() {
    if (redirecting) return;
    redirecting = true;
    for (const key of ['access_token', 'nickname', 'user_id']) localStorage.removeItem(key);
    window.alert('로그인이 만료되었거나 유효하지 않습니다. 다시 로그인해 주세요.');
    window.location.replace('/login');
  }

  window.fetch = async (input, options) => {
    const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, window.location.href);
    const protectedApi = url.origin === window.location.origin && /^\/(chat|study|personality-report)(\/|$)/.test(url.pathname);
    const response = await originalFetch(input, options);
    if (protectedApi && response.status === 401) requireLogin();
    return response;
  };

  // localStorage에 닉네임이 남아 있는 것만으로 로그인 상태를 판단하지 않는다.
  document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname !== '/mypage_edit') return;
    const token = localStorage.getItem('access_token');
    if (!token) {
      requireLogin();
      return;
    }
    window.fetch('/study/diary/check-condition', {
      headers: {Authorization: `Bearer ${token}`},
    }).catch(() => {
      // 네트워크 장애는 인증 실패로 처리하지 않는다. 실제 동작 시 재시도 가능.
    });
  });
})();
