import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()


def _sqlite_file_path(database_url: str) -> str | None:
    # Deliberately not urlparse+lstrip("/") -- that combination silently breaks an absolute
    # POSIX sqlite path (sqlite:////abs/path has 4 slashes, so the parsed path component itself
    # already carries a leading slash before the real path; lstrip("/") strips both, turning
    # "/abs/path" into the relative path "abs/path"). Found and fixed this exact bug in
    # mcp-toolkit-ai's sql_query server after it passed on Windows but failed in Linux CI --
    # porting the fix here instead of the buggy version that's still in docuchat-ai/prreview-ai's
    # db.py. Everything after the literal "sqlite:///" prefix is the filesystem path verbatim,
    # per SQLAlchemy's own convention.
    if ":memory:" in database_url or not database_url.startswith("sqlite:///"):
        return None
    return database_url[len("sqlite:///") :]


def _ensure_sqlite_dir_exists(database_url: str) -> None:
    db_path = _sqlite_file_path(database_url)
    if db_path is None:
        return
    parent = Path(db_path).parent
    if str(parent) not in ("", "."):
        os.makedirs(parent, exist_ok=True)


_ensure_sqlite_dir_exists(settings.database_url)
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_engine() -> Engine:
    """FastAPI-resolvable so background tasks (which open their own Session outside the
    request's Depends(get_session) lifecycle) can be handed the correct engine -- including the
    in-memory test engine when overridden in tests."""
    return engine


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
