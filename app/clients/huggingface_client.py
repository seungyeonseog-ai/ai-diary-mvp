# app/clients/huggingface_client.py
import os
from typing import List
from langchain_huggingface import HuggingFaceEmbeddings
from app.config.settings import settings

# 선택사항: HF_HOME 고정은 유지해도 됨
os.environ["HF_HOME"] = settings.huggingface_cache_path

class HuggingFaceClient:
    def __init__(self, model_name: str = "jhgan/ko-sroberta-multitask"):
        self.model_name = model_name
        self.emb = HuggingFaceEmbeddings(
            model_name=model_name,
            cache_folder=settings.huggingface_cache_path,
            model_kwargs={
                "device": "cpu",                    # ✅ cache_folder는 여기서 제거
                "trust_remote_code": False,
            },
            encode_kwargs={
                "normalize_embeddings": True,
            },
        )
        print(f"[Embed] model={self.model_name} (CPU)")

    def embed(self, text: str) -> List[float]:
        return self.emb.embed_query(text)

    def embed_many(self, texts: List[str]) -> List[List[float]]:
        return self.emb.embed_documents(texts)
