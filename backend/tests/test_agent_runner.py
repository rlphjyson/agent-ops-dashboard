import asyncio
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.models import Run, RunEvent
from app.services import agent_runner, mcp_config, run_registry
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
    NormalizedEvent(
        kind="system", payload={"tools": ["mcp__kb__search_notes"], "session_id": "sess-abc"}
    ),
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
        payload={
            "is_error": False,
            "result_text": "Done.",
            "cost_usd": 0.01,
            "num_turns": 2,
            "session_id": "sess-abc",
        },
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
    assert run.session_id == "sess-abc"


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


async def test_continue_run_resumes_with_the_stored_session_id(
    session: Session, test_engine, run: Run
) -> None:
    run.status = "completed"
    run.session_id = "sess-abc"
    session.add(run)
    session.commit()
    engine = FakeAgentEngine(SUCCESS_EVENTS)

    await agent_runner.continue_run(run.id, "a follow-up question", test_engine, agent_engine=engine)

    assert engine.received_prompt == "a follow-up question"
    assert engine.received_resume_session_id == "sess-abc"


async def test_continue_run_emits_a_user_text_event_before_the_engine_runs(
    session: Session, test_engine, run: Run
) -> None:
    run.status = "completed"
    run.session_id = "sess-abc"
    session.add(run)
    session.commit()
    engine = FakeAgentEngine(SUCCESS_EVENTS)

    await agent_runner.continue_run(run.id, "a follow-up question", test_engine, agent_engine=engine)

    events = session.exec(
        select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.id)  # type: ignore[arg-type]
    ).all()
    assert events[0].kind == "user_text"
    assert events[0].payload_json == '{"text": "a follow-up question"}'
    assert [e.kind for e in events[1:]] == [
        "system",
        "tool_use",
        "tool_result",
        "assistant_text",
        "result",
    ]


async def test_continue_run_marks_completed_and_updates_the_session_id_again(
    session: Session, test_engine, run: Run
) -> None:
    run.status = "completed"
    run.session_id = "sess-abc"
    session.add(run)
    session.commit()
    engine = FakeAgentEngine(SUCCESS_EVENTS)

    await agent_runner.continue_run(run.id, "another turn", test_engine, agent_engine=engine)

    session.refresh(run)
    assert run.status == "completed"
    assert run.result_text == "Done."
    # SUCCESS_EVENTS' result always reports "sess-abc" -- a real resumed session keeps the same id,
    # but the assignment (`... or run.session_id`) is what matters here, not the literal value.
    assert run.session_id == "sess-abc"


async def test_continue_run_emits_error_and_leaves_status_untouched_without_a_session_id(
    session: Session, test_engine, run: Run
) -> None:
    run.status = "completed"
    session.add(run)
    session.commit()
    engine = FakeAgentEngine(SUCCESS_EVENTS)

    await agent_runner.continue_run(run.id, "a follow-up question", test_engine, agent_engine=engine)

    session.refresh(run)
    assert run.status == "completed"  # unchanged -- this is a defensive path, not a failure
    assert engine.received_prompt is None  # never even asked to run

    events = session.exec(select(RunEvent).where(RunEvent.run_id == run.id)).all()
    assert len(events) == 1
    assert events[0].kind == "error"


async def test_continue_run_returns_quietly_for_unknown_run_id(test_engine) -> None:
    engine = FakeAgentEngine(SUCCESS_EVENTS)

    await agent_runner.continue_run("does-not-exist", "hi", test_engine, agent_engine=engine)

    assert engine.received_prompt is None


async def test_cancelling_the_task_marks_the_run_cancelled_and_emits_a_cancelled_event(
    session: Session, test_engine, run: Run
) -> None:
    engine = FakeAgentEngine(SUCCESS_EVENTS[:1], hang_after_events=True)

    task = asyncio.create_task(agent_runner.execute_run(run.id, run.prompt, test_engine, agent_engine=engine))
    # Let the task actually start and reach the hang point (past the first yielded event) before
    # cancelling it -- otherwise there's no guarantee it's mid-await inside agent_engine.run() yet.
    for _ in range(10):
        await asyncio.sleep(0)

    task.cancel()
    # Deliberately not wrapped in pytest.raises(CancelledError): _run_agent_loop's handler
    # catches and swallows it (see the comment there for why), so the task completes normally.
    await task

    session.refresh(run)
    assert run.status == "cancelled"
    assert run.completed_at is not None
    # Regression test for a real, live-caught bug: a cancelled run never reaches a "result"
    # event, and session_id was originally only captured there -- leaving every cancelled run
    # permanently un-resumable ("no resumable session to continue yet", even seconds after a
    # real session had genuinely started). Captured from the "system" event instead/as well now.
    assert run.session_id == "sess-abc"

    events = session.exec(
        select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.id)  # type: ignore[arg-type]
    ).all()
    assert events[-1].kind == "cancelled"


async def test_a_cancelled_run_can_be_continued_afterward(
    session: Session, test_engine, run: Run
) -> None:
    engine = FakeAgentEngine(SUCCESS_EVENTS[:1], hang_after_events=True)
    task = asyncio.create_task(agent_runner.execute_run(run.id, run.prompt, test_engine, agent_engine=engine))
    for _ in range(10):
        await asyncio.sleep(0)
    task.cancel()
    await task
    session.refresh(run)
    assert run.status == "cancelled"

    follow_up_engine = FakeAgentEngine(SUCCESS_EVENTS)
    await agent_runner.continue_run(run.id, "still there?", test_engine, agent_engine=follow_up_engine)

    assert follow_up_engine.received_resume_session_id == "sess-abc"
    session.refresh(run)
    assert run.status == "completed"


async def test_cancelling_the_run_calls_the_engines_registered_kill_hook(
    session: Session, test_engine, run: Run
) -> None:
    # End-to-end confirmation that _run_agent_loop wires an engine's register_killer through to
    # run_registry: this is what makes Stop actually kill a real CliAgentEngine subprocess
    # promptly, rather than relying solely on task cancellation (confirmed live not to interrupt
    # a pending subprocess stdout read promptly on Windows -- see run_registry's docstring).
    killed = False

    def _kill() -> None:
        nonlocal killed
        killed = True

    engine = FakeAgentEngine(SUCCESS_EVENTS[:1], hang_after_events=True, killer=_kill)

    task = asyncio.create_task(agent_runner.execute_run(run.id, run.prompt, test_engine, agent_engine=engine))
    for _ in range(10):
        await asyncio.sleep(0)

    assert run_registry.cancel(run.id) is True
    assert killed is True

    await task
    session.refresh(run)
    assert run.status == "cancelled"
