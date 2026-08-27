from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import get_engine, get_session
from app.main import app
from app.models import User
from app.security import create_access_token, hash_password
from app.services.agent_runner import get_agent_engine
from tests.fakes import FakeAgentEngine


@pytest.fixture(name="test_engine")
def test_engine_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="session")
def session_fixture(test_engine) -> Generator[Session, None, None]:
    with Session(test_engine) as session:
        yield session


@pytest.fixture(name="fake_agent_engine")
def fake_agent_engine_fixture() -> FakeAgentEngine:
    return FakeAgentEngine(events=[])


@pytest.fixture(name="client")
def client_fixture(
    session: Session,
    test_engine,
    fake_agent_engine: FakeAgentEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    def get_session_override() -> Generator[Session, None, None]:
        yield session

    # The app's lifespan validates the sibling mcp-toolkit-ai checkout exists at startup (fail
    # loudly, not lazily) -- most tests have nothing to do with that and shouldn't depend on a
    # real filesystem checkout being present just for the app to boot.
    monkeypatch.setattr("app.main.mcp_config.resolve_toolkit_path", lambda: Path("/fake-toolkit"))
    monkeypatch.setattr("app.main.mcp_config.load_toolkit_servers", lambda path: {})

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_engine] = lambda: test_engine
    # Without this, POST /runs's background task would try to construct a *real* engine (spawn a
    # real subprocess, possibly call a real API) -- every test route goes through the fake here.
    app.dependency_overrides[get_agent_engine] = lambda: fake_agent_engine

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture(name="user")
def user_fixture(session: Session) -> User:
    user = User(email="test@example.com", hashed_password=hash_password("password123"))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(user: User) -> dict[str, str]:
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}
