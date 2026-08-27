from collections.abc import AsyncIterator

from app.services.agent_engines.base import NormalizedEvent
from app.services.mcp_config import ServerConfig


class FakeAgentEngine:
    """Yields a canned sequence of NormalizedEvents, standing in for either real engine (the
    rest of the system only ever depends on the AgentEngine Protocol, never on which real engine
    this is faking). Pass `raise_after=N` to raise a RuntimeError after the Nth event instead of
    completing normally -- exercises agent_runner's failure path."""

    def __init__(self, events: list[NormalizedEvent], raise_after: int | None = None) -> None:
        self.events = events
        self.raise_after = raise_after
        self.received_prompt: str | None = None
        self.received_servers: dict[str, ServerConfig] | None = None

    async def run(
        self, prompt: str, mcp_servers: dict[str, ServerConfig]
    ) -> AsyncIterator[NormalizedEvent]:
        self.received_prompt = prompt
        self.received_servers = mcp_servers
        for i, event in enumerate(self.events):
            yield event
            if self.raise_after is not None and i == self.raise_after:
                raise RuntimeError("engine crashed mid-run")
