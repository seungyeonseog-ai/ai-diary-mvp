"""격리 검증 전용. 실키/원문을 기록하지 않고 호출 상한을 영속적으로 제한한다."""
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, Response

MODEL = 'gpt-5.6-luna'
MAX_CALLS = 50
MAX_BODY = 60000
MAX_OUTPUT = 1800
DB = Path('/budget/calls.db')
app = FastAPI()


def reserve(data, size):
    if (size > MAX_BODY or data.get('model') != MODEL or
        not 1 <= data.get('max_completion_tokens', 0) <= MAX_OUTPUT or
        data.get('n', 1) != 1 or data.get('tools') or data.get('functions')):
        raise ValueError('Request outside approved validation budget')
    DB.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, status INTEGER, input_tokens INTEGER, output_tokens INTEGER)')
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT count(*) FROM calls').fetchone()[0] >= MAX_CALLS:
            raise ValueError('Approved validation call limit reached')
        call_id = db.execute('INSERT INTO calls(status) VALUES(NULL)').lastrowid
        db.commit()
    return call_id


def record(call_id, status, usage=None):
    usage = usage or {}
    with closing(sqlite3.connect(DB)) as db:
        db.execute('UPDATE calls SET status=?, input_tokens=?, output_tokens=? WHERE id=?',
                   (status, usage.get('prompt_tokens'), usage.get('completion_tokens'), call_id))
        db.commit()
    print(json.dumps({'call':call_id,'status':status,'usage':usage}), flush=True)


@app.post('/v1/chat/completions')
async def completions(request: Request):
    raw = await request.body()
    try:
        data = json.loads(raw)
        call_id = reserve(data, len(raw))
    except (ValueError, TypeError):
        raise HTTPException(429, 'Validation budget rejected request') from None
    if data.get('stream'):
        data['stream_options'] = {'include_usage':True}
    async def content():
        status, usage = 502, None
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                async with client.stream('POST', 'https://api.openai.com/v1/chat/completions',
                    headers={'Authorization':'Bearer '+os.environ['REAL_OPENAI_API_KEY']}, json=data) as upstream:
                    status = upstream.status_code
                    if status != 200:
                        raise RuntimeError('Upstream AI request failed')
                    async for line in upstream.aiter_lines():
                        if line.startswith('data: ') and line != 'data: [DONE]':
                            try:
                                parsed = json.loads(line[6:])
                                if parsed.get('usage'): usage = parsed['usage']
                            except ValueError: pass
                        yield line+'\n'
        finally:
            record(call_id,status,usage)
    if data.get('stream'):
        return StreamingResponse(content(),media_type='text/event-stream')
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post('https://api.openai.com/v1/chat/completions',
            headers={'Authorization':'Bearer '+os.environ['REAL_OPENAI_API_KEY']},json=data)
    if response.status_code == 200:
        record(call_id,200,response.json().get('usage'))
        return Response(response.content,media_type='application/json')
    record(call_id,response.status_code)
    raise HTTPException(502,'Upstream AI request failed')
