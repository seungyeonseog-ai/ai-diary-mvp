"""본인 이용 상태 조회. 가격/결제와 분리된 기능 권한 계약."""
from typing import Literal
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from sqlalchemy.orm import Session
from app.core.connection import get_db
from app.api.dependencies.auth_dependencies import get_current_user
from app.models.db.user_model import User
from app.services.access_service import access, PLANS, selected_plan, choose_plan, ensure_account
from app.models.db.access_model import AccountAccess, PilotSurvey
from app.services.writing_service import transaction
from app.services.posthog_capture import capture_writing_event
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


class ExperienceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    help_score: int = Field(strict=True, ge=1, le=5)
    reason: str = Field(default="", max_length=1000)
    kakao_interest: Literal["yes", "unsure", "no"]


def survey_available(db, user_id, now):
    expires_at = access(db, user_id, now)["trial_expires_at"]
    return bool(expires_at and now.isoformat() >= expires_at)


@router.get("/pilot-survey")
def pilot_survey(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(PilotSurvey, user.id)
    return {"available": survey_available(db, user.id, get_kst_now()),
            "experience_submitted": bool(row and row.experience_at),
            "plan_submitted": bool(row and row.plan_at)}


def survey_response(session, user_id, now):
    if not survey_available(session, user_id, now):
        raise HTTPException(409, "무료 체험이 끝난 뒤 참여할 수 있어요.")
    row = session.get(PilotSurvey, user_id)
    if row is None:
        row = PilotSurvey(user_id=user_id)
        session.add(row)
    return row


@router.post("/pilot-survey/experience")
def submit_experience(data: ExperienceInput, background_tasks: BackgroundTasks,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = get_kst_now()
    with transaction(db.get_bind(), user.id) as session:
        row = survey_response(session, user.id, now)
        first_submission = row.experience_at is None
        if first_submission:
            row.help_score = data.help_score
            row.reason = data.reason.strip()
            row.kakao_interest = data.kakao_interest
            row.experience_at = now
    if first_submission:
        background_tasks.add_task(capture_writing_event, "pilot_experience_submitted",
                                  user.id, "pilot", now, help_score=data.help_score,
                                  kakao_interest=data.kakao_interest)
    return {"submitted": True}


@router.post("/pilot-survey/plan")
def submit_pilot_plan(data: ChoiceInput, background_tasks: BackgroundTasks,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = get_kst_now()
    try:
        with transaction(db.get_bind(), user.id) as session:
            row = survey_response(session, user.id, now)
            first_submission = row.plan_at is None
            if first_submission:
                choose_plan(session, user.id, data.request_id, data.plan, now)
                row.plan = data.plan
                row.plan_at = now
    except ValueError:
        raise HTTPException(409, "선택을 저장하지 못했어요. 다시 시도해 주세요.") from None
    if first_submission:
        background_tasks.add_task(capture_writing_event, "pilot_plan_submitted",
                                  user.id, "pilot", now, plan=data.plan,
                                  selected_features=list(PLANS[data.plan]))
    return {"submitted": True}


@router.post('/onboarding')
def complete_onboarding(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    with transaction(db.get_bind(),user.id) as session:
        row=ensure_account(session,session.get(User,user.id))
        row.onboarding_completed_at=row.onboarding_completed_at or get_kst_now()
    return {'complete':True}
