"""모델을 실제 앱 프로세스에서 준비한 뒤 HTTP/Worker 준비 신호를 연다."""
import gc
import os
import runpy
import sys
import time


def warmup():
    from deploy.preflight import validate
    validate()
    start=time.monotonic()
    from app.clients.huggingface_client import HuggingFaceClient
    model=HuggingFaceClient()
    if len(model.embed("배포 프로세스 준비 확인")) != 768:
        raise RuntimeError("Unexpected embedding dimension")
    del model
    gc.collect()
    print(f"PASS: process model warmup ({time.monotonic()-start:.1f}s)",flush=True)


def main():
    kind=sys.argv[1]
    if kind not in ("web","worker"):raise ValueError("Unknown deployment process")
    warmup()
    if kind=="web":
        import uvicorn
        uvicorn.run(os.environ.get("ASGI_APP_MODULE","app.main:app"),host="0.0.0.0",port=8000,workers=1,log_level="info")
    else:
        module=os.environ.get("CELERY_APP_MODULE","app.services.celery_app:celery")
        sys.argv=["celery","-A",module,"worker","--loglevel=info","--pool=solo","--concurrency=1","--hostname=diary-compose@%h"]
        runpy.run_module("celery",run_name="__main__")


if __name__=="__main__":main()
