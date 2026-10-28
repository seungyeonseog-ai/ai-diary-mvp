from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.token_utils import decode_token
from app.models.schemas.auth_schema import UserInToken
from app.core.connection import get_db
from app.models.db.user_model import User
from jose import JWTError

# FastAPI가 토큰을 가져오는 방식 지정
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# 의존성 함수 정의 ( 토큰해독 ->user_id 추출)
def resolve_token_user(token: str, db: Session) -> User:
    try:
        payload = decode_token(token)
        user_data = UserInToken(**payload)
        user = db.get(User, user_data.user_id)
        if not user:
            raise HTTPException(status_code=401, detail="인증 실패: 유효하지 않은 사용자입니다.")
        return user
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="인증 실패: 유효하지 않은 토큰입니다.")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    return resolve_token_user(token, db)
