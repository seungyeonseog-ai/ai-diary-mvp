"""운영 이미지에 제품 자산/FTS5는 있고 검증 API/비밀/원본 DB는 없는지 확인."""
from pathlib import Path
import importlib.metadata
import importlib.util
import json
import sqlite3

assert importlib.util.find_spec("validation") is None
for name in (".env",".env.production",".local-check",".venv-local",".git","test.db","backups"):
    assert not Path("/app",name).exists(),name
assert Path('/app/static/images/space/lamp-default-v1.png').is_file()
assert Path('/app/templates/writing.html').is_file()
assert importlib.metadata.version('torch')=='2.7.1+cpu'
assert importlib.metadata.version('chromadb')=='1.0.15'
db=sqlite3.connect(':memory:')
db.execute("CREATE VIRTUAL TABLE check_fts USING fts5(body, tokenize='trigram')")
db.execute("INSERT INTO check_fts VALUES('산책기록 합성검증')")
assert db.execute("SELECT count(*) FROM check_fts WHERE check_fts MATCH '산책기록'").fetchone()[0]==1
db.close()
print(json.dumps({'production_image_has_no_validation_or_local_data':True,'product_assets':True,'cpu_torch':True,'sqlite_fts5_trigram':True}))
