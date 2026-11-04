# app/clients/huggingface_client.py
import os
from functools import lru_cache
from threading import RLock
from typing import List
from langchain_huggingface import HuggingFaceEmbeddings
from app.config.settings import settings

# 선택사항: HF_HOME 고정은 유지해도 됨
os.environ["HF_HOME"] = settings.huggingface_cache_path
_model_lock = RLock()


@lru_cache(maxsize=1)
def _load_model(model_name, cache_path):
    # CPU/정규화/모델 선택은 유지하고 무거운 객체만 프로세스 안에서 재사용한다.
    model = HuggingFaceEmbeddings(
        model_name=model_name, cache_folder=cache_path,
        model_kwargs={"device":"cpu", "trust_remote_code":False},
        encode_kwargs={"normalize_embeddings":True},
    )
    print(f"[Embed] model={model_name} (CPU, process cache)")
    return model

class HuggingFaceClient:
    def __init__(self, model_name: str = "jhgan/ko-sroberta-multitask"):
        self.model_name = model_name
        # 첫 동시 요청도 중복 모델을 만들지 않는다. 인코딩 호출 자체는 잠그지 않는다.
        with _model_lock:
            self.emb = _load_model(model_name, settings.huggingface_cache_path)

    def embed(self, text: str) -> List[float]:
        return self.emb.embed_query(text)

    def embed_many(self, texts: List[str]) -> List[List[float]]:
        return self.emb.embed_documents(texts)
