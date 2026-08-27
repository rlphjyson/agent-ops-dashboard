import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlmodel import Session

from app.models import Run, RunEvent
from app.services import mcp_config
from app.services.agent_engines.base import AgentEngine


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


async def execute_run(
    run_id: str,
    prompt: str,
    engine: Engine,
    agent_engine: AgentEngine | None = None,
    on_event: OnEvent = _noop,
) -> None:
    """Runs one submitted task to completion, persisting a RunEvent per normalized event and
    finalizing the Run's status. Opens its own Session (not the request-scoped `Depends`) since
    it runs as a FastAPI background task outlasting the request that triggered it -- same shape
    as prreview-ai's webhook -> _process_review.

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

        try:
            toolkit_path = mcp_config.resolve_toolkit_path()
            mcp_servers = mcp_config.load_toolkit_servers(toolkit_path)
        except Exception as exc:
            _fail(session, run, str(exc))
            _emit(session, run_id, "error", {"message": str(exc)}, on_event)
            return

        try:
            async for event in agent_engine.run(prompt, mcp_servers):
                _emit(session, run_id, event.kind, event.payload, on_event)
                if event.kind == "result":
                    run.status = "failed" if event.payload.get("is_error") else "completed"
                    run.result_text = event.payload.get("result_text")
                    run.cost_usd = event.payload.get("cost_usd")
                    run.num_turns = event.payload.get("num_turns")
                    run.completed_at = datetime.now(UTC)
                    session.add(run)
                    session.commit()
        except Exception as exc:
            # No `result` event ever arrived (bad path, subprocess spawn failure, API error) --
            # without this, the frontend would see "running" forever.
            _fail(session, run, str(exc))
            _emit(session, run_id, "error", {"message": str(exc)}, on_event)
