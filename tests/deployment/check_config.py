"""실제 Compose가 해석한 구성의 격리·환경·볼륨 및 누락키 오류를 확인한다."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[2]
env=dict(os.environ)
for key in ('OPENAI_API_KEY','SECRET_KEY','MATABUS_IMAGE','WEB_PORT','OPENAI_MODEL','COMPOSE_PROJECT_NAME'):env.pop(key,None)
base=['docker','compose','--project-directory',str(root),'--project-name','matabus-validation',
      '--env-file',str(root/'.local-check/docker-validation/validation.env'),'-f',str(root/'docker-compose.yml')]
for validation in (False,True):
    command=base+(['-f',str(root/'docker-compose.validation.yml')] if validation else [])
    config=json.loads(subprocess.check_output(command+['config','--format','json'],env=env))
    services=config['services']
    for name in ('web','celery-worker','celery-beat'):
        service=services[name]
        values=service['environment']
        assert values['DATABASE_URL']=='sqlite:////data/app.db'
        assert values['SPARSE_DB_PATH']=='/data/sparse_fts.db'
        assert values['CELERY_BROKER_URL']=='redis://redis:6379/0'
        assert values['OPENAI_API_KEY']=='synthetic-docker-validation-no-real-key'
        assert service['build']['target']==('validation' if validation else 'runtime')
        assert any(v['source']=='app_data' and v['target']=='/data' for v in service['volumes'])
    assert not services['redis'].get('ports') and not services['chroma'].get('ports')
    assert services['web']['ports'][0]['host_ip']=='127.0.0.1'
    for name in ('web','celery-worker'):
        assert services[name]['depends_on']['db-init']['condition']=='service_completed_successfully'
        assert services[name]['depends_on']['model-init']['condition']=='service_completed_successfully'
    assert services['celery-beat']['command']==['python','-m','deploy.beat']
    if validation:
        assert services['web']['environment']['DEPLOYMENT_VALIDATION']=='1'
        assert services['web']['environment']['OPENAI_BASE_URL']=='http://127.0.0.1:9/blocked'
    print('PASS: actual Compose '+('validation' if validation else 'runtime')+' configuration',flush=True)
with tempfile.NamedTemporaryFile() as empty:
    command=['docker','compose','--project-directory',str(root),'--env-file',empty.name,'-f',str(root/'docker-compose.yml'),'config','--quiet']
    result=subprocess.run(command,env=env,capture_output=True)
    assert result.returncode!=0
print('PASS: missing deployment credentials rejected without printing secrets',flush=True)
