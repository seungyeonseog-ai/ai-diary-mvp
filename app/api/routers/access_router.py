"""본인 이용 상태 조회. 가격/결제와 분리된 기능 권한 계약."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from sqlalchemy.orm import Session
from app.core.connection import get_db
from app.api.dependencies.auth_dependencies import get_current_user
from app.models.db.user_model import User
from app.services.access_service import access, PLANS, selected_plan, choose_plan, ensure_account
from app.models.db.access_model import AccountAccess
from app.services.writing_service import transaction
from app.utils.time_utils import get_kst_now

router = APIRouter(prefix="/account", tags=["access"])
LABELS = {"free":"무료", "dialogue_encouragement":"추가 대화 + 저녁 응원",
          "dialogue_weekly":"추가 대화 + 주간 차트", "encouragement_weekly":"저녁 응원 + 주간 차트",
          "super":"슈퍼패스"}


@router.get("/access")
def current(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = get_kst_now()
    row = db.get(AccountAccess,user.id)
    return {**access(db,user.id,now), **selected_plan(db,user.id), "server_now":now.isoformat(),
            "onboarding_complete":bool(row and row.onboarding_completed_at),
            "selection_mode":"preference_only",
            "plans":[{"id":key,"label":LABELS[key],"features":list(features)} for key,features in PLANS.items()]}


class ChoiceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: StrictStr = Field(min_length=1,max_length=80,pattern=r"\S")
    plan: Literal["free","dialogue_encouragement","dialogue_weekly","encouragement_weekly","super"]


@router.post("/plan-choice")
def choose(data: ChoiceInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        with transaction(db.get_bind(),user.id) as session:
            return choose_plan(session,user.id,data.request_id,data.plan,get_kst_now())
    except ValueError:
        raise HTTPException(409,"같은 요청 ID에 다른 이용권을 선택했어요. 상태를 다시 확인해 주세요.") from None


@router.post('/onboarding')
def complete_onboarding(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    with transaction(db.get_bind(),user.id) as session:
        row=ensure_account(session,session.get(User,user.id))
        row.onboarding_completed_at=row.onboarding_completed_at or get_kst_now()
    return {'complete':True}
