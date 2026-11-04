"""처음 한 번 모델을 준비한다. 후속 앱 프로세스는 오프라인 캐시를 쓴다."""
if __name__ == "__main__":
    from app.clients.huggingface_client import HuggingFaceClient
    vector = HuggingFaceClient().embed("배포 모델 준비 확인")
    if len(vector) != 768:
        raise RuntimeError("Unexpected embedding dimension")
    print("PASS: CPU model cache ready (768 dimensions)")
