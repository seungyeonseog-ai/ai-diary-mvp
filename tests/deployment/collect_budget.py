"""프록시 예산 볼륨의 숫자 집계만 출력한다. 키/원문 없음."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

with closing(sqlite3.connect('file:/budget/calls.db?mode=ro',uri=True)) as db:
    calls,inputs,outputs,unknown=db.execute('SELECT count(*),coalesce(sum(input_tokens),0),coalesce(sum(output_tokens),0),sum(input_tokens IS NULL OR output_tokens IS NULL) FROM calls').fetchone()
    statuses=dict(db.execute('SELECT coalesce(status,0),count(*) FROM calls GROUP BY status'))
print(json.dumps({'at_utc':datetime.now(timezone.utc).isoformat(),'calls':calls,'input_tokens':inputs,
    'output_tokens':outputs,'unmeasured_calls':unknown or 0,'statuses':statuses,
    'estimated_usd_uncached':round((inputs*.20+outputs*1.20)/1000000,8),
    'approved_cumulative_usd':2,'maximum_calls':30,'pricing':'https://developers.openai.com/api/docs/models/gpt-5.6-luna'}))
