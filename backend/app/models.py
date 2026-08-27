import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=_now)


class Run(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    owner_id: str = Field(foreign_key="user.id", index=True)
    prompt: str
    status: str = "queued"  # queued | running | completed | failed | cancelled
    result_text: str | None = None
    error_message: str | None = None
    cost_usd: float | None = None
    num_turns: int | None = None
    # The underlying claude session id, captured from a "result" event -- lets a later
    # POST /runs/{id}/messages resume this exact conversation (--resume / ClaudeAgentOptions.resume)
    # instead of starting a fresh, context-free one. None until the first result arrives.
    session_id: str | None = None
    created_at: datetime = Field(default_factory=_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RunEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)  # autoincrement -- also the cursor
    run_id: str = Field(foreign_key="run.id", index=True)
    kind: str  # system | assistant_text | tool_use | tool_result | result | error
    payload_json: str
    created_at: datetime = Field(default_factory=_now)
