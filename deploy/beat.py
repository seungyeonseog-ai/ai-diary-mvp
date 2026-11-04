"""공유 상태 디렉터리의 OS 잠금으로 Beat 중복 실행을 막는다."""
import os
import sys


if __name__ == "__main__":
    import fcntl
    fd = os.open("/state/beat.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another Beat owns this state volume")
    os.set_inheritable(fd, True)
    module = os.environ.get("CELERY_APP_MODULE", "app.services.celery_app:celery")
    os.execv(sys.executable, [sys.executable, "-m", "celery", "-A", module, "beat",
        "--loglevel=info", "--schedule=/state/celerybeat-schedule", "--pidfile=/tmp/celerybeat.pid"])
