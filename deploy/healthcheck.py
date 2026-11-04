"""컨테이너 내부 상태 검사. 원문/환경 비밀값을 출력하지 않는다."""
import json
import os
from pathlib import Path
import socket
import sys
from urllib.request import urlopen


def heartbeat(host="chroma", port=8000):
    with urlopen(f"http://{host}:{port}/api/v2/heartbeat", timeout=3) as response:
        assert response.status == 200
        json.load(response)


def check(kind):
    if kind == "chroma":
        return heartbeat("127.0.0.1")
    if kind == "beat":
        pid = int(Path("/tmp/celerybeat.pid").read_text().strip())
        args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        module = os.environ.get("CELERY_APP_MODULE", "app.services.celery_app:celery").encode()
        assert b"beat" in args and module in args
        os.kill(pid, 0)
        return
    import redis
    redis.Redis(host=os.environ.get("REDIS_HOST", "redis"), port=6379,
                socket_timeout=3, socket_connect_timeout=3).ping()
    if kind == "worker":
        from celery import Celery
        node = "diary-compose@" + socket.gethostname()
        replies = Celery("health", broker=os.environ["CELERY_BROKER_URL"]).control.ping(
            destination=[node], timeout=5)
        assert any(reply.get(node, {}).get("ok") == "pong" for reply in replies)
    elif kind == "web":
        with urlopen("http://127.0.0.1:8000/", timeout=3) as response:
            assert response.status == 200
        from sqlalchemy import create_engine, text
        engine = create_engine(os.environ["DATABASE_URL"])
        try:
            with engine.connect() as conn:
                assert conn.execute(text("SELECT id FROM daily_activation WHERE id=1")).first()
        finally:
            engine.dispose()
        heartbeat()
    else:
        raise ValueError("Unknown health probe")


if __name__ == "__main__":
    try:
        check(sys.argv[1])
    except Exception as exc:
        print("unhealthy: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
