import asyncio
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlmodel import Session

from app.models import Run, RunEvent
from app.services import mcp_config, run_registry
from app.services.agent_engines.base import AgentEngine

logger = logging.getLogger(__name__)


@dataclass
class PersistedEvent:
    """A plain, session-independent snapshot of a just-persisted RunEvent -- deliberately not the
    RunEvent ORM instance itself, which becomes a DetachedInstanceError waiting to happen the
    moment anything touches its attributes after execute_run's `with Session(...)` block exits
    (confirmed the hard way: session.refresh() marks all attributes for lazy-reload, and a
    callback consuming events after the run finishes is exactly the intended usage). This is also
    just what event_bus/the WS relay actually want: JSON-serializable data, not an ORM object."""

    id: int
    run_id: str
    kind: str
    payload: dict
    created_at: datetime


OnEvent = Callable[[PersistedEvent], None]


def _noop(event: PersistedEvent) -> None:
    return None


def get_agent_engine() -> AgentEngine:
    # FastAPI-resolvable (Depends(get_agent_engine)) so routers don't hardcode which engine gets
    # used -- and so tests can override it with a FakeAgentEngine, same shape as prreview-ai's
    # Depends(get_review_engine).
    return default_agent_engine()


def default_agent_engine() -> AgentEngine:
    # Engine selection is auto-detected, not a separate setting: a real ANTHROPIC_API_KEY means
    # the Agent SDK can authenticate with it directly, so use it; otherwise fall back to shelling
    # out to the `claude` CLI, which reuses whatever Claude Code subscription login is already on
    # this machine. Confirmed via a real Phase 0 spike that this specific pairing is the safe
    # one -- the CLI engine's tool-restriction flags are confirmed to properly sandbox the agent,
    # while a bare key-less SDK call was confirmed NOT to (this design never takes that path).
    if os.environ.get("ANTHROPIC_API_KEY"):
        from app.services.agent_engines.sdk import SdkAgentEngine

        return SdkAgentEngine()
    from app.services.agent_engines.cli import CliAgentEngine

    return CliAgentEngine()


def _emit(session: Session, run_id: str, kind: str, payload: dict, on_event: OnEvent) -> None:
    run_event = RunEvent(run_id=run_id, kind=kind, payload_json=json.dumps(payload))
    session.add(run_event)
    session.commit()
    session.refresh(run_event)
    assert run_event.id is not None
    snapshot = PersistedEvent(
        id=run_event.id,
        run_id=run_event.run_id,
        kind=run_event.kind,
        payload=payload,
        created_at=run_event.created_at,
    )
    on_event(snapshot)


def _fail(session: Session, run: Run, message: str) -> None:
    run.status = "failed"
    run.error_message = message
    run.completed_at = datetime.now(UTC)
    session.add(run)
    session.commit()


def _cancel(session: Session, run: Run) -> None:
    run.status = "cancelled"
    run.completed_at = datetime.now(UTC)
    session.add(run)
    session.commit()


async def _run_agent_loop(
    session: Session,
    run: Run,
    agent_engine: AgentEngine,
    prompt: str,
    resume_session_id: str | None,
    on_event: OnEvent,
) -> None:
    """Shared by execute_run (a run's first turn) and continue_run (every turn after): resolves
    the toolkit's servers, iterates the engine's event stream, and finalizes the Run's status.
    Only what differs between a fresh run and a continuation -- whether a session is resumed, and
    whether a synthetic user_text event needs recording first -- lives in the two callers below.
    """
    run_id = run.id

    # Registers *this* coroutine's own task so POST /runs/{id}/cancel has something to cancel().
    # execute_run/continue_run are invoked via FastAPI's BackgroundTasks, which awaits them
    # sequentially inside the same task that's already handling the original HTTP request rather
    # than spawning a separate one -- so this is that request's own long-lived task, still alive
    # here well after its response was already sent back to the client.
    task = asyncio.current_task()
    if task is not None:
        run_registry.register(run_id, task)

    try:
        toolkit_path = mcp_config.resolve_toolkit_path()
        mcp_servers = mcp_config.load_toolkit_servers(toolkit_path)
    except Exception as exc:
        # logger.exception (not just str(exc)) because some exceptions stringify to "" with
        # no arguments (e.g. a bare CancelledError) -- without the traceback in the server
        # log, a failure like that is completely silent and undiagnosable from the API alone.
        logger.exception("Failed to resolve mcp-toolkit-ai servers for run %s", run_id)
        message = str(exc) or f"{type(exc).__name__} (see server log for the full traceback)"
        _fail(session, run, message)
        _emit(session, run_id, "error", {"message": message}, on_event)
        return

    def _register_killer(kill: Callable[[], None]) -> None:
        run_registry.set_kill_hook(run_id, kill)

    try:
        async for event in agent_engine.run(prompt, mcp_servers, resume_session_id, _register_killer):
            _emit(session, run_id, event.kind, event.payload, on_event)
            # Every stream-json line (CLI engine) carries a session_id, starting with the very
            # first ("system") event -- captured here, generically, rather than only on
            # "result", so a run *cancelled* mid-flight (which never reaches a "result" event)
            # still ends up with a resumable session_id. A real, live-caught bug: continuing a
            # cancelled run always failed with "no resumable session" because this only checked
            # the result event before, and a cancelled run never produces one.
            new_session_id = event.payload.get("session_id")
            if new_session_id:
                run.session_id = new_session_id
                session.add(run)
                session.commit()
            if event.kind == "result":
                run.status = "failed" if event.payload.get("is_error") else "completed"
                run.result_text = event.payload.get("result_text")
                run.cost_usd = event.payload.get("cost_usd")
                run.num_turns = event.payload.get("num_turns")
                run.completed_at = datetime.now(UTC)
                session.add(run)
                session.commit()
    except asyncio.CancelledError:
        # The user hit Stop -- run_registry.cancel() cancelled the task this coroutine is running
        # on while it was mid-await inside agent_engine.run(). Deliberately caught and swallowed
        # rather than re-raised: this task is shared with the original HTTP request that already
        # sent its response long before the run actually finished (see the registration above),
        # so letting CancelledError propagate out of it would surface as a noisy, misleading
        # "unhandled exception in ASGI application" in the server log for what is actually a
        # normal, successful stop -- the DB update and the emitted event below already fully
        # capture the outcome.
        logger.info("Run %s cancelled by user", run_id)
        _cancel(session, run)
        _emit(session, run_id, "cancelled", {"message": "Stopped by user."}, on_event)
    except Exception as exc:
        # No `result` event ever arrived (bad path, subprocess spawn failure, API error) --
        # without this, the frontend would see "running" forever.
        logger.exception("Agent engine failed mid-run for run %s", run_id)
        message = str(exc) or f"{type(exc).__name__} (see server log for the full traceback)"
        _fail(session, run, message)
        _emit(session, run_id, "error", {"message": message}, on_event)


async def execute_run(
    run_id: str,
    prompt: str,
    engine: Engine,
    agent_engine: AgentEngine | None = None,
    on_event: OnEvent = _noop,
) -> None:
    """Runs one submitted task's first turn to completion, persisting a RunEvent per normalized
    event and finalizing the Run's status. Opens its own Session (not the request-scoped
    `Depends`) since it runs as its own asyncio.Task outlasting the request that scheduled it --
    same shape as prreview-ai's webhook -> _process_review.

    `agent_engine` is the test seam: defaults to the real, auto-detected engine, but a test
    passes a FakeAgentEngine instead and doesn't need to know or care which real engine it's
    standing in for.
    """
    agent_engine = agent_engine or default_agent_engine()

    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            return
        run.status = "running"
        run.started_at = datetime.now(UTC)
        session.add(run)
        session.commit()

        await _run_agent_loop(session, run, agent_engine, prompt, None, on_event)


async def continue_run(
    run_id: str,
    prompt: str,
    engine: Engine,
    agent_engine: AgentEngine | None = None,
    on_event: OnEvent = _noop,
) -> None:
    """Sends a follow-up prompt to a run that already completed at least one turn, resuming the
    same underlying claude session (--resume / ClaudeAgentOptions.resume) instead of starting a
    fresh, context-free one. The router already checked run.status/run.session_id before
    scheduling this, but it's re-checked here too since this runs independently afterward."""
    agent_engine = agent_engine or default_agent_engine()

    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            return
        if not run.session_id:
            message = "This run has no resumable session to continue yet."
            _emit(session, run_id, "error", {"message": message}, on_event)
            return

        _emit(session, run_id, "user_text", {"text": prompt}, on_event)
        run.status = "running"
        session.add(run)
        session.commit()

        await _run_agent_loop(session, run, agent_engine, prompt, run.session_id, on_event)
