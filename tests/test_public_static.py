import tempfile
import unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from app.core.public_static import public_static


class PublicStaticTests(unittest.TestCase):
    def test_static_cache_compression_and_private_stream_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, 'app.js').write_text('const text="' + 'abc' * 3000 + '";')
            app = FastAPI()
            app.mount('/static', public_static(temp))
            @app.get('/private')
            def private(): return {'private': True}
            @app.get('/stream')
            def stream():
                return StreamingResponse(iter(['data: first\n\n', 'data: last\n\n']), media_type='text/event-stream')
            with TestClient(app) as client:
                result = client.get('/static/app.js', headers={'Accept-Encoding': 'gzip'})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.headers['content-encoding'], 'gzip')
                self.assertIn('max-age=86400', result.headers['cache-control'])
                cached = client.get('/static/app.js', headers={'If-None-Match': result.headers['etag']})
                self.assertEqual(cached.status_code, 304)
                self.assertNotIn('cache-control', client.get('/private').headers)
                stream = client.get('/stream')
                self.assertNotIn('content-encoding', stream.headers)
                self.assertIn('data: first', stream.text)
                self.assertEqual(client.get('/static/missing.js').status_code, 404)


if __name__ == '__main__': unittest.main()
