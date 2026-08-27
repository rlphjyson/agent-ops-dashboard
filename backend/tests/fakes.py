import asyncio
from collections.abc import AsyncIterator, Callable

from app.services.agent_engines.base import NormalizedEvent
from app.services.mcp_config import ServerConfig


class FakeAgentEngine:
    """Yields a canned sequence of NormalizedEvents, standing in for either real engine (the
    rest of the system only ever depends on the AgentEngine Protocol, never on which real engine
    this is faking). Pass `raise_after=N` to raise a RuntimeError after the Nth event instead of
    completing normally -- exercises agent_runner's failure path. Pass `hang_after_events=True`
    to block forever (on an asyncio.Event that's never set) once every event has been yielded,
    instead of returning -- lets a test cancel the surrounding task mid-run to exercise the stop
    path, the way a real engine would still be running when a user hits Stop. Pass `killer=` (a
    zero-arg callable) to simulate an engine that has something to forcibly kill -- it's handed
    to `register_killer` exactly like CliAgentEngine hands over `process.kill`, letting a test
    verify run_registry actually calls it on cancel()."""

    def __init__(
        self,
        events: list[NormalizedEvent],
        raise_after: int | None = None,
        hang_after_events: bool = False,
        killer: Callable[[], None] | None = None,
    ) -> None:
        self.events = events
        self.raise_after = raise_after
        self.hang_after_events = hang_after_events
        self.killer = killer
        self.received_prompt: str | None = None
        self.received_servers: dict[str, ServerConfig] | None = None
        self.received_resume_session_id: str | None = None

    async def run(
        self,
        prompt: str,
        mcp_servers: dict[str, ServerConfig],
        resume_session_id: str | None = None,
        register_killer: Callable[[Callable[[], None]], None] | None = None,
    ) -> AsyncIterator[NormalizedEvent]:
        self.received_prompt = prompt
        self.received_servers = mcp_servers
        self.received_resume_session_id = resume_session_id
        if self.killer is not None and register_killer is not None:
            register_killer(self.killer)
        for i, event in enumerate(self.events):
            yield event
            if self.raise_after is not None and i == self.raise_after:
                raise RuntimeError("engine crashed mid-run")
        if self.hang_after_events:
            await asyncio.Event().wait()
