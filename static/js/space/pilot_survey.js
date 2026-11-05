import {id,json} from './ui.js?v=20261104-ui2';

export async function showPilotSurvey(same) {
  const modal = document.getElementById('pilot-survey');
  const status = await json('/account/pilot-survey');
  if (!same() || !status.available || (status.plan_submitted && status.experience_submitted)) return;

  const plan = modal.querySelector('#plan-form');
  const experience = modal.querySelector('#experience-form');
  const combo = modal.querySelector('#pilot-combo');
  const requestId = id();
  let saving = false;
  const show = () => {
    plan.closest('section').hidden = status.plan_submitted || !status.experience_submitted;
    experience.closest('section').hidden = status.experience_submitted;
    if (status.plan_submitted && status.experience_submitted) modal.close();
  };
  const close = () => modal.close();
  const update = () => {
    const data = new FormData(plan);
    const isCombo = data.get('plan') === 'combo';
    combo.hidden = combo.disabled = !isCombo;
    const selected = combo.querySelectorAll('input:checked').length;
    for (const input of combo.querySelectorAll('input')) {
      input.disabled = isCombo && selected >= 2 && !input.checked;
    }
    plan.querySelector('[type=submit]').disabled = saving || !data.get('plan') || (isCombo && selected !== 2);
    experience.querySelector('[type=submit]').disabled = saving || !experience.checkValidity();
  };
  for (const button of modal.querySelectorAll('[data-close]')) button.addEventListener('click', close);
  window.addEventListener('space:identity-cleared', close, {once:true});
  for (const form of [plan, experience]) form.addEventListener('input', update);

  async function submit(event, form, path, payload, completion) {
    event.preventDefault();
    if (saving || !same() || !modal.open) return;
    saving = true;
    update();
    const message = form.querySelector('.form-status');
    message.textContent = '';
    try {
      await json('/account/pilot-survey/' + path, {method:'POST',data:payload});
      if (!same()) return;
      status[completion] = true;
      if (modal.open) show();
    } catch {
      if (same()) message.textContent = '저장하지 못했어요. 다시 시도해 주세요.';
    } finally {
      saving = false;
      if (same()) update();
    }
  }
  experience.addEventListener('submit', event => {
    const data = new FormData(experience);
    void submit(event, experience, 'experience', {
      help_score:Number(data.get('help')), reason:data.get('reason'), kakao_interest:data.get('kakao')
    }, 'experience_submitted');
  });
  plan.addEventListener('submit', event => {
    const data = new FormData(plan);
    const choice = data.get('plan');
    const features = ['dialogue', 'encouragement', 'weekly'].filter(feature => data.getAll('feature').includes(feature));
    const selected = choice === 'combo' ? features.join('_') : choice;
    void submit(event, plan, 'plan', {request_id:requestId,plan:selected}, 'plan_submitted');
  });
  show();
  update();
  modal.showModal();
}
