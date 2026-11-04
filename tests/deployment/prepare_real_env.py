"""기존 로컬 키를 출력하지 않고 Git 제외 검증 env에만 전달한다."""
from pathlib import Path
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[2]
values = dotenv_values(root/'.env')
key = values.get('OPENAI_API_KEY')
if not key or not key.startswith('sk-'):
    raise RuntimeError('A real local API key is not available')
if values.get('OPENAI_MODEL','gpt-5.6-luna') != 'gpt-5.6-luna':
    raise RuntimeError('Configured model differs from approved pricing; review required')
if any(c in key for c in '\r\n\"\''):
    raise RuntimeError('Invalid API key encoding')
target = root/'.local-check/docker-validation/real.env'
target.write_text((root/'.local-check/docker-validation/validation.env').read_text(encoding='utf-8')
                  +'\nREAL_OPENAI_API_KEY='+key+'\n',encoding='utf-8')
target.chmod(0o600)
print('PASS: private real validation environment prepared; key not printed')
