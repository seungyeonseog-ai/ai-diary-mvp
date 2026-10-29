from pydantic import BaseModel
from typing import Optional

class DiaryResponse(BaseModel):
    diary_id: int
    content: str

class DiarySevenResponse(BaseModel):
    report_id: int
    emotions: list
    scores: list
    keywords: list
    summary: str

class EncouragementResponse(BaseModel):
    encouragement_id: int
    content: str
from pydantic import ConfigDict, Field, StrictStr, field_validator

class ManualDiaryInput(BaseModel):
    # 사용자가 보낸 user_id/source_type은 저장 권한에 사용하지 않는다.
    model_config = ConfigDict(extra="ignore")
    content: StrictStr = Field(min_length=1, max_length=50000)

    @field_validator("content")
    @classmethod
    def nonblank_content(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("일기 내용을 입력해주세요.")
        return value
