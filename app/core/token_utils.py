from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config.settings import settings
from app.models.schemas.auth_schema import UserInToken

SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


def encode_token(user_id: int):
    payload = UserInToken(user_id=user_id).model_dump()
    # JWT 만료는 UTC 기준으로 계산한다.
    payload["exp"] = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        return jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            options={"require_exp": True},
        )
    except JWTError:
        raise ValueError("유효하지 않은 토큰입니다.") from None
