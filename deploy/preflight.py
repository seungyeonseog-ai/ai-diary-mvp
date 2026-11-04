"""필수 런타임 값 검사. 비밀값은 출력하지 않는다."""
import os


def validate(environment=None):
    env = os.environ if environment is None else environment
    key = env.get("OPENAI_API_KEY", "").strip()
    secret = env.get("SECRET_KEY", "").strip()
    validation = env.get("DEPLOYMENT_VALIDATION") == "1"
    if not key or (not validation and any(word in key.lower() for word in ("your-", "placeholder", "synthetic"))):
        raise ValueError("A real OPENAI_API_KEY is required")
    if len(secret) < 32 or secret == "your-super-secret-key-here":
        raise ValueError("SECRET_KEY must be a private random value of at least 32 characters")
    if env.get("CELERY_BROKER_URL") != "redis://redis:6379/0":
        raise ValueError("Compose broker must use the internal redis service")
    if env.get("DATABASE_URL") != "sqlite:////data/app.db":
        raise ValueError("Compose database must use /data/app.db")
    if env.get("SPARSE_DB_PATH") != "/data/sparse_fts.db":
        raise ValueError("Compose sparse database must use the shared /data volume")


if __name__ == "__main__":
    validate()
    print("PASS: required deployment settings present")
