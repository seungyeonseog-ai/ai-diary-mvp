"""이번 UI 조작의 저장 불변·선택 권한·실제 AI 주간 자료형/원본연결/계정격리 대조."""
import hashlib
import json
import math
from pathlib import Path
import httpx

root=Path('.local-check/docker-validation')
records=json.loads((root/'ui-server-evidence.json').read_text(encoding='utf-8'))
own=[r for r in records if r['user']=='screenflow20261104b']
baseline=next(r for r in own if r['label']=='saved-baseline')
for label in ('after-extra-one','after-extra-two'):
    row=next(r for r in own if r['label']==label)
    assert row['diaries']==baseline['diaries']
for label,plan in (('plan-dialogue-weekly','dialogue_weekly'),('plan-super','super')):
    row=next(r for r in own if r['label']==label)
    assert row['access']['selected_plan']==plan
    for key in ('trial_started_at','trial_expires_at','features'):
        assert row['access'][key]==baseline['access'][key]
rewritten=next(r for r in own if r['label']=='rewritten-saved')
assert rewritten['diary_total']==1 and rewritten['aggregate']['photos']==1
assert rewritten['diaries'][0]['id']!=baseline['diaries'][0]['id']
with httpx.Client(base_url='http://127.0.0.1:18000',timeout=180) as client:
    def login(name):
        response=client.post('/login',json={'username':name,'password':'SyntheticDocker!2026'})
        response.raise_for_status();client.headers['Authorization']='Bearer '+response.json()['access_token']
    def get(path):
        response=client.get(path);response.raise_for_status();return response.json()
    login('screenflow20261104b')
    access=get('/account/access')
    assert access['selected_plan']=='super'
    assert access['trial_expires_at']==baseline['access']['trial_expires_at']
    assert access['features']==baseline['access']['features']
    diary=get('/writing/diaries/'+str(rewritten['diaries'][0]['id']))
    assert diary['state']=='saved'
    assert hashlib.sha256(diary['body'].encode()).hexdigest()==rewritten['diaries'][0]['body_sha256']
    assert client.get('/study/seven-day-report/1').status_code==404
    login('weeklyscreen20261104a')
    access=get('/account/access')
    assert access['trial_state']=='expired' and access['features']==[]
    assert access['trial_expires_at']=='2026-11-04T00:00:00'
    result=get('/study/seven-day-report/1')
    assert get('/study/weekly/latest')['weekly_analysis']['id']==1
    report=result['weekly_analysis'];daily=result['diary_analyses']
    assert report['period_start']=='2026-10-28' and report['period_end']=='2026-11-03'
    assert {d['date_str'] for d in daily}=={'2026-10-28','2026-10-30','2026-11-03'}
    for day in daily:
        assert len(day['emotions'])==len(day['scores'])>0
        assert all(type(v) in (float,int) and math.isfinite(v) and -1<=v<=1 for v in day['scores'])
        assert len(day['keywords'])==len(day['keyword_descriptions'])>0
        assert day['summary']
    assert set(report['comprehensive_pattern_result']['_source_report_ids'])=={d['id'] for d in daily}
    assert report['emotion_trend']['trend'] and report['keyword_patterns']['insights'] and report['overall_assessment']
    notices=get('/daily/notices')
    assert any(n['kind']=='weekly' and n['result_id']==1 for n in notices['items'])
    assert get('/daily/inbox')['state']=='unavailable'
    assert client.get('/writing/diaries/'+str(rewritten['diaries'][0]['id'])).status_code==404
    client.headers.pop('Authorization')
    assert client.get('/study/seven-day-report/1').status_code==401
summary={'ui_diary_unchanged_after_extras':True,'ui_discard_rewrite_saved':True,
    'ui_plan_changes_preserved_rights':True,'weekly_real_ai_days':3,'weekly_source_mapping_valid':True,
    'actual_ai_numeric_types_valid':True,'weekly_readable_after_expiry':True,
    'new_paid_features_disabled':True,'cross_account_404':True,'unauthenticated_401':True,
    'natural_wall_clock_verification':False}
(root/'ui-backend-verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
