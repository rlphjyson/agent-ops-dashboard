from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.models import Run, RunEvent
from app.services import agent_runner, mcp_config
from app.services.agent_engines.base import NormalizedEvent
from tests.fakes import FakeAgentEngine


@pytest.fixture(autouse=True)
def _fake_toolkit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_config, "resolve_toolkit_path", lambda: Path("/fake-toolkit"))
    monkeypatch.setattr(mcp_config, "load_toolkit_servers", lambda path: {})


@pytest.fixture(name="run")
def run_fixture(session: Session, user) -> Run:
    run = Run(owner_id=user.id, prompt="do the thing")
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


SUCCESS_EVENTS = [
    NormalizedEvent(kind="system", payload={"tools": ["mcp__kb__search_notes"]}),
    NormalizedEvent(
        kind="tool_use",
        payload={"tool_use_id": "t1", "name": "mcp__kb__search_notes", "input": {"query": "x"}},
    ),
    NormalizedEvent(
        kind="tool_result", payload={"tool_use_id": "t1", "content": "found it", "is_error": False}
    ),
    NormalizedEvent(kind="assistant_text", payload={"text": "Found it in note x."}),
    NormalizedEvent(
        kind="result",
        payload={"is_error": False, "result_text": "Done.", "cost_usd": 0.01, "num_turns": 2},
    ),
]


async def test_execute_run_persists_events_in_order(session: Session, test_engine, run: Run) -> None:
    engine = FakeAgentEngine(SUCCESS_EVENTS)

    await agent_runner.execute_run(run.id, run.prompt, test_engine, agent_engine=engine)

    session.refresh(run)
    events = session.exec(select(RunEvent).where(RunEvent.run_id == run.id)).all()
    assert [e.kind for e in events] == [
        "system",
        "tool_use",
        "tool_result",
        "assistant_text",
        "result",
    ]


async def test_execute_run_marks_completed_on_success_result(
    session: Session, test_engine, run: Run
) -> None:
    engine = FakeAgentEngine(SUCCESS_EVENTS)

    await agent_runner.execute_run(run.id, run.prompt, test_engine, agent_engine=engine)

    session.refresh(run)
    assert run.status == "completed"
    assert run.result_text == "Done."
    assert run.cost_usd == 0.01
    assert run.num_turns == 2
    assert run.completed_at is not None


async def test_execute_run_marks_failed_when_result_event_is_error(
    session: Session, test_engine, run: Run
) -> None:
    engine = FakeAgentEngine(
        [
            NormalizedEvent(
                kind="result",
                payload={"is_error": True, "result_text": "blew up", "cost_usd": 0.0, "num_turns": 1},
            )
        ]
    )

    await agent_runner.execute_run(run.id, run.prompt, test_engine, agent_engine=engine)

    session.refresh(run)
    assert run.status == "failed"


async def test_execute_run_marks_failed_when_engine_raises_mid_run(
    session: Session, test_engine, run: Run
) -> None:
    engine = FakeAgentEngine(SUCCESS_EVENTS[:2], raise_after=1)

    await agent_runner.execute_run(run.id, run.prompt, test_engine, agent_engine=engine)

    session.refresh(run)
    assert run.status == "failed"
    assert run.error_message == "engine crashed mid-run"

    events = session.exec(select(RunEvent).where(RunEvent.run_id == run.id)).all()
    assert events[-1].kind == "error"


async def test_execute_run_marks_failed_when_toolkit_not_found(
    session: Session, test_engine, run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise() -> Path:
        raise mcp_config.ToolkitNotFoundError("mcp-toolkit-ai checkout not found")

    monkeypatch.setattr(mcp_config, "resolve_toolkit_path", _raise)
    engine = FakeAgentEngine(SUCCESS_EVENTS)

    await agent_runner.execute_run(run.id, run.prompt, test_engine, agent_engine=engine)

    session.refresh(run)
    assert run.status == "failed"
    assert "mcp-toolkit-ai checkout not found" in (run.error_message or "")
    # The engine should never have been asked to run at all -- the toolkit lookup failed first.
    assert engine.received_prompt is None


async def test_execute_run_invokes_on_event_callback_for_every_event(
    session: Session, test_engine, run: Run
) -> None:
    engine = FakeAgentEngine(SUCCESS_EVENTS)
    received = []

    await agent_runner.execute_run(
        run.id, run.prompt, test_engine, agent_engine=engine, on_event=received.append
    )

    assert [e.kind for e in received] == [
        "system",
        "tool_use",
        "tool_result",
        "assistant_text",
        "result",
    ]


async def test_execute_run_passes_prompt_and_servers_to_engine(
    session: Session, test_engine, run: Run
) -> None:
    engine = FakeAgentEngine(SUCCESS_EVENTS)

    await agent_runner.execute_run(run.id, run.prompt, test_engine, agent_engine=engine)

    assert engine.received_prompt == run.prompt
    assert engine.received_servers == {}


async def test_execute_run_returns_quietly_for_unknown_run_id(test_engine) -> None:
    engine = FakeAgentEngine(SUCCESS_EVENTS)

    await agent_runner.execute_run("does-not-exist", "hi", test_engine, agent_engine=engine)

    assert engine.received_prompt is None
