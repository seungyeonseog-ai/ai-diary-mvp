from app.config.settings import settings
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies.auth_dependencies import get_current_user
from app.core.connection import get_db
from app.models.db.study_model import PersonalityReport
from app.models.db.user_model import User

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/personality-report/{report_id}")
async def get_personality_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """본인 소유 리포트만 반환하고 타인 리포트의 존재도 노출하지 않는다."""
    if not settings.upper_reports_enabled:
        raise HTTPException(status_code=404, detail="리포트 기능은 준비 중입니다.")
    try:
        report = db.query(PersonalityReport).filter(
            PersonalityReport.id == report_id,
            PersonalityReport.user_id == current_user.id,
        ).first()
        if report is None:
            raise HTTPException(status_code=404, detail="Personality report not found")

        result = report.report_result
        return {
            "query": report.query,
            "emotional_pattern": result.get("정서적 패턴", ""),
            "personality_tendency": result.get("성향", ""),
            "unconscious_insight": result.get("무의식적 통찰", ""),
            "user_id": report.user_id,
            "timestamp": report.timestamp,
            "date_str": report.date_str,
        }
    except HTTPException:
        raise
    except Exception:
        logger.error("Personality report retrieval failed", exc_info=False)
        raise HTTPException(status_code=500, detail="리포트를 불러오지 못했습니다.")
