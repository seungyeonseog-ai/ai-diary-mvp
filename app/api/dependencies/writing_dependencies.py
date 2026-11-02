"""새 작성으로 전환한 사용자의 구형 작성 API 우회 방지. 읽기 API는 유지."""
from fastapi import Depends,HTTPException
from sqlalchemy.orm import Session
from app.core.connection import get_db
from app.api.dependencies.auth_dependencies import get_current_user
from app.models.db.writing_model import Writing


def require_legacy_creation(db:Session=Depends(get_db),user=Depends(get_current_user)):
    if db.query(Writing.id).filter_by(user_id=user.id).first():
        raise HTTPException(409,"새 작성 화면에서 이야기를 이어주세요. 홈페이지의 나의 공간 입장하기를 눌러주세요.")
