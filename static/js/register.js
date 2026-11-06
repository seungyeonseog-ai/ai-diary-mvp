// 예전 캐시의 일반 script에서도 파싱되도록 동적 import를 사용한다.
async function dialog(...args){
 if(!document.getElementById('ui-dialog'))for(const name of ['space-ui','detail-ui','ui-polish']){
  const link=document.createElement('link');link.rel='stylesheet';link.href=`/static/css/${name}.css?v=20261104-ui2`;document.head.append(link);
 }
 return (await import('./space/ui.js?v=20261104-ui2')).dialog(...args);
}
let submittingRegistration=false;
// register.html에서 분리된 JS 코드
// 아래는 register.html의 <script>...</script> 내부 전체 JS 코드입니다.

// 비밀번호 유효성 검사 함수
function validatePassword(password) {
  const requirements = {
    english: /[A-Za-z]/.test(password),
    number: /\d/.test(password),
    special: /[!@#$%^&*(),.?":{}|<>]/.test(password),
    repeat: !/(\d)\1{2,}/.test(password)
  };

  // 요구사항 표시 업데이트
  document.getElementById('req-english').className =
    `requirement ${requirements.english ? 'valid' : 'invalid'}`;
  document.getElementById('req-number').className =
    `requirement ${requirements.number ? 'valid' : 'invalid'}`;
  document.getElementById('req-special').className =
    `requirement ${requirements.special ? 'valid' : 'invalid'}`;
  document.getElementById('req-repeat').className =
    `requirement ${requirements.repeat ? 'valid' : 'invalid'}`;

  return Object.values(requirements).every(req => req);
}

// 비밀번호 일치 확인 함수
function checkPasswordMatch() {
  const password = document.getElementById('password').value;
  const confirmPassword = document.getElementById('password_confirm').value;
  const matchDiv = document.getElementById('password-match');

  if (confirmPassword === '') {
    matchDiv.textContent = '';
    matchDiv.className = 'password-match';
    return false;
  }

  if (password === confirmPassword) {
    matchDiv.textContent = '✓ 비밀번호가 일치합니다';
    matchDiv.className = 'password-match valid';
    return true;
  } else {
    matchDiv.textContent = '✗ 비밀번호가 일치하지 않습니다';
    matchDiv.className = 'password-match invalid';
    return false;
  }
}

// 폼 유효성 검사
function validateForm() {
  const password = document.getElementById('password').value;
  const isPasswordValid = validatePassword(password);
  const isPasswordMatch = checkPasswordMatch();
  const fields = ['username','email','nickname'].map(id=>document.getElementById(id));
  const areFieldsValid = fields.every(field=>field.value.trim()!==''&&field.checkValidity())
    && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(document.getElementById('email').value);

  const submitBtn = document.getElementById('submit-btn');
  if (!submittingRegistration && areFieldsValid && isPasswordValid && isPasswordMatch) {
    submitBtn.disabled = false;
    submitBtn.className = 'submit-btn active';
  } else {
    submitBtn.disabled = true;
    submitBtn.className = 'submit-btn';
  }
}

for(const name of ['username','email','nickname']){
  document.getElementById(name)?.addEventListener('input',validateForm);
  document.getElementById(name)?.addEventListener('change',validateForm);
}

// 이벤트 리스너 설정
if (document.getElementById('password')) {
  document.getElementById('password').addEventListener('input', function() {
    validatePassword(this.value);
    checkPasswordMatch();
    validateForm();
  });
}

if (document.getElementById('password_confirm')) {
  document.getElementById('password_confirm').addEventListener('input', function() {
    checkPasswordMatch();
    validateForm();
  });
}

// 폼 제출 처리
if (document.getElementById("registerForm")) {
  document.getElementById("registerForm").addEventListener("submit", async function(e) {
    e.preventDefault();
    const submit=document.getElementById('submit-btn');if(submittingRegistration||submit.disabled)return;submittingRegistration=true;submit.disabled=true;

    const formData = new FormData(this);
    const data = {
      username: formData.get("username"),
      password: formData.get("password"),
      email: formData.get("email"),
      nickname: formData.get("nickname"),
      invite_code: formData.get("invite_code") || null
    };

    try {
      const response = await fetch("/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(data)
      });

      const result = await response.json();

      if (!response.ok) {
        if (Array.isArray(result.detail)) {
          const errorMessages = result.detail.map(e => e.msg).join("\n");
          await dialog('회원가입을 완료하지 못했어요',errorMessages);
        } else {
          await dialog('회원가입을 완료하지 못했어요',typeof result.detail==='string'?result.detail:result.message||'입력한 내용을 확인해 주세요.');
        }
      } else {
        await dialog('회원가입이 완료됐어요',result.message || '로그인하고 나의 공간을 시작해 보세요.');
        window.location.href = "/login";
      }

    } catch (error) {
      await dialog('서버에 연결하지 못했어요','입력한 내용은 그대로 두고 잠시 후 다시 시도해 주세요.');
    } finally {
      submittingRegistration=false;
      validateForm();
    }
  });
}

// 페이지 로드 시 초기 상태 설정
window.onload = function() {
  validateForm();
};
