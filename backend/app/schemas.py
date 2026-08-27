from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RunCreateRequest(BaseModel):
    prompt: str = Field(min_length=1)


class RunResponse(BaseModel):
    id: str
    prompt: str
    status: str
    result_text: str | None
    error_message: str | None
    cost_usd: float | None
    num_turns: int | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class RunEventResponse(BaseModel):
    id: int
    run_id: str
    kind: str
    payload: dict
    created_at: datetime
