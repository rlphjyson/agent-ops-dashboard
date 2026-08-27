from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from app.services.mcp_config import ServerConfig

# The contract every engine (SdkAgentEngine, CliAgentEngine, and any test fake) must produce,
# regardless of which underlying mechanism generated it -- everything downstream of AgentEngine
# (persistence, the WS relay, the frontend) only ever sees NormalizedEvents.
#
# kind -> payload shape:
#   system        {"tools": list[str], ...}                       -- informational, not acted on
#   assistant_text {"text": str}
#   tool_use      {"tool_use_id": str, "name": str, "input": dict}
#   tool_result   {"tool_use_id": str, "content": Any, "is_error": bool}
#   result        {"is_error": bool, "result_text": str, "cost_usd": float | None, "num_turns": int | None}
#   error         {"message": str}                                 -- synthetic, engine-run failure


@dataclass
class NormalizedEvent:
    kind: str
    payload: dict


class AgentEngine(Protocol):
    def run(
        self, prompt: str, mcp_servers: dict[str, ServerConfig]
    ) -> AsyncIterator[NormalizedEvent]: ...
