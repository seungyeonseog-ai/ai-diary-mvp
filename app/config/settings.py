from pydantic_settings import BaseSettings
from typing import Optional
import os
from pydantic import Field
from pydantic import field_validator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    # 환경 구분
    environment: str = "development"

    # 데이터베이스 설정
    database_url: str = "sqlite:///./test.db"

    # API 키 설정
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    openai_model: str = "gpt-5.6-luna"
    mixtral_token: str = Field(default="", env="MIXTRAL_TOKEN")
    mixtral_endpoint: str = Field(default="", env="MIXTRAL_ENDPOINT")

    # 보안 설정
    secret_key: str = Field(default="your-secret-key", env="SECRET_KEY")
    access_token_expire_minutes: int = 30

    # Redis 설정
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # 미제공 기능: 코드/기존 데이터는 보존하고 실행은 기본 중지한다.
    music_recommendations_enabled: bool = False
    upper_reports_enabled: bool = False

    # 애플리케이션 설정
    app_name: str = "Matabus Chat API"
    debug: bool = True
    log_level: str = "INFO"

    @field_validator("database_url", mode="before")
    @classmethod
    def resolve_database_url(cls, value):
        # 웹/Worker를 다른 작업 디렉터리에서 실행해도 같은 DB를 사용한다.
        from sqlalchemy.engine import make_url
        url = make_url(value)
        if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
            path = Path(url.database).expanduser()
            if not path.is_absolute():
                url = url.set(database=(PROJECT_ROOT / path).resolve().as_posix())
        return url.render_as_string(hide_password=False)

    # 성능 설정 , 실제 사용되고 있있지 않음
    rate_limit_per_minute: int = 60
    max_concurrent_requests: int = 10

    # Chroma 연결 설정
    chroma_host: Optional[str] = None  # 예: "127.0.0.1" (None이면 파일모드 사용)
    chroma_port: int = 8000
    chroma_path: str = str(PROJECT_ROOT / ".local-check" / "chroma_db")
    sparse_db_path: str = str(PROJECT_ROOT / ".local-check" / "chroma_db" / "sparse_fts.db")
    huggingface_cache_path: str = str(PROJECT_ROOT / ".local-check" / "huggingface_cache")
    chroma_allow_reset: bool = False

    @field_validator("chroma_path", "sparse_db_path", "huggingface_cache_path", mode="before")
    @classmethod
    def resolve_local_path(cls, value):
        path = Path(value).expanduser()
        return str(path if path.is_absolute() else PROJECT_ROOT / path)

    class Config:
        env_file = str(PROJECT_ROOT / ".env")
        case_sensitive = False




settings = Settings()
