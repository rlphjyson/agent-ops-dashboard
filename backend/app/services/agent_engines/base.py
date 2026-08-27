from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Protocol

from app.services.mcp_config import ServerConfig

# The contract every engine (SdkAgentEngine, CliAgentEngine, and any test fake) must produce,
# regardless of which underlying mechanism generated it -- everything downstream of AgentEngine
# (persistence, the WS relay, the frontend) only ever sees NormalizedEvents.
#
# kind -> payload shape:
#   system        {"tools": list[str], "session_id": str | None}    -- the first event of any run;
#                  session_id is captured here too (not just from "result") so a run *cancelled*
#                  before ever reaching a result event still ends up with a resumable session_id.
#   assistant_text {"text": str}
#   tool_use      {"tool_use_id": str, "name": str, "input": dict}
#   tool_result   {"tool_use_id": str, "content": Any, "is_error": bool}
#   result        {"is_error": bool, "result_text": str, "cost_usd": float | None, "num_turns": int | None,
#                  "session_id": str | None}  -- session_id lets a later run resume this conversation
#   error         {"message": str}                                 -- synthetic, engine-run failure
#
# agent_runner also persists two synthetic kinds that no engine ever yields itself:
#   user_text     {"text": str}                -- a follow-up prompt, recorded so it shows in the timeline
#   cancelled     {"message": str}              -- the run was stopped by the user mid-flight


@dataclass
class NormalizedEvent:
    kind: str
    payload: dict


class AgentEngine(Protocol):
    def run(
        self,
        prompt: str,
        mcp_servers: dict[str, ServerConfig],
        resume_session_id: str | None = None,
        register_killer: Callable[[Callable[[], None]], None] | None = None,
    ) -> AsyncIterator[NormalizedEvent]:
        """register_killer, if given, is called at most once with a zero-arg callable that
        forcibly terminates whatever real OS process this run is backed by -- an engine that
        spawns a subprocess (CliAgentEngine) should call it as soon as that process exists, so
        run_registry.cancel() can kill it directly instead of relying solely on task
        cancellation, which was confirmed live to NOT promptly interrupt a pending subprocess
        stdout read on Windows (see run_registry's module docstring). An engine with nothing to
        forcibly kill (SdkAgentEngine, FakeAgentEngine) just never calls it."""
        ...
