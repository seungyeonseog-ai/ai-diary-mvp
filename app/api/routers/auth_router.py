from app.utils.time_utils import get_kst_now
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.schemas.auth_schema import UserCreate
from app.services.auth_service import create_user, authenticate_user
from app.core.connection import SessionLocal
from app.models.db.user_model import User
from datetime import datetime
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import Request
from app.models.schemas.auth_schema import LoginInput
import logging
logging.basicConfig(level=logging.INFO)
from app.api.dependencies.auth_dependencies import get_current_user





templates = Jinja2Templates(directory="templates")


# 1. API 라우터 객체 생성
router = APIRouter()


@router.get("/account/me")
def account_me(current_user: User = Depends(get_current_user)):
    return {"id":current_user.id, "nickname":current_user.nickname}

# 2. DB 세션 주입 함수
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 3. 회원가입 API 라우트
@router.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    # 중복된 username 확인
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 아이디입니다.")

    create_user(db, user)

    logging.info("✏️ register 라우터 완료")
    # 가공된 응답 변환
    return {"message": "회원가입이 성공적으로 완료되었습니다."}


# 4. 로그인 라우터

@router.post("/login")
def login(data: LoginInput, db: Session = Depends(get_db)):
    print("🚀 로그인 요청 도착")
    try:
        token = authenticate_user(db, data.username, data.password)
        print("✅ 토큰 생성 성공")

        # username으로 유저 정보 조회 (nickname 포함)
        user = db.query(User).filter(User.username == data.username).first()
        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

        return {
            "access_token": token,     # 기존 JWT
            "nickname": user.nickname,  # ✅ 환영 문구용 닉네임 추가
            "user_id": user.id  # 이거 추가!
        }

    except HTTPException as he:
        raise he

    except Exception as e:
        print("❌ 서버 내부 예외 발생:", e)
        raise HTTPException(status_code=500, detail="서버 좇가은 라우터에서 예외발생")






# 5. 로그아웃 라우터 ( 이후  확장용도 , 로그인 테이블에 같이 넣는거임 )


@router.post("/logout")
def logout(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.models.db.login_log import LoginLog
    log = db.query(LoginLog).filter(LoginLog.user_id == current_user.id).order_by(LoginLog.login_time.desc(), LoginLog.id.desc()).first()
    if log:
        # 재시도/동시 요청에서도 최초 기록을 보존한다.
        db.query(LoginLog).filter(LoginLog.id == log.id, LoginLog.logout_time.is_(None)).update(
            {LoginLog.logout_time: get_kst_now()}, synchronize_session=False
        )
        db.commit()
    print ("✅ 로그아웃 완료 : db 기록 성공")
    return {"message": "로그아웃 완료 (기록용)"}







print("✅ register_router.py 로딩 완료")
print("✅ router 객체:", router )
