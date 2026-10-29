from pydantic import BaseModel, Field

class MessageInput(BaseModel):
    message: str

class TurnInput(BaseModel):
    turn: int

class ChatResponseInput(BaseModel):
    turn: int = Field(gt=0, strict=True)
    session_id: str = Field(min_length=1, max_length=100)
