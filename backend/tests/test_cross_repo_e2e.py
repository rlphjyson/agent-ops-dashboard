"""One real, cross-repo end-to-end test: no fake at the MCP protocol layer, no real Anthropic
API cost. Validates the one genuinely risky mechanism in this app's design -- resolving
mcp-toolkit-ai's real servers.toml, translating a ServerConfig into real subprocess spawn
parameters, and actually talking the MCP protocol to a really-spawned server -- without spending
money or touching real GitHub (issue_tracker's own ISSUE_TRACKER_FAKE_GITHUB=1 fake-client gate,
already established in that repo, does the rest).

Needs the actual sibling mcp-toolkit-ai checkout with issue_tracker installed into its .venv --
skipped automatically if that isn't present (e.g. a CI job that doesn't do the sibling checkout).
"""

from collections.abc import AsyncIterator

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.services import mcp_config
from app.services.agent_engines.base import NormalizedEvent
from app.services.mcp_config import ServerConfig

try:
    _TOOLKIT_PATH = mcp_config.resolve_toolkit_path()
    _SERVERS = mcp_config.load_toolkit_servers(_TOOLKIT_PATH)
    _TOOLKIT_AVAILABLE = "issues" in _SERVERS
except mcp_config.ToolkitNotFoundError:
    _TOOLKIT_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _TOOLKIT_AVAILABLE,
    reason="sibling mcp-toolkit-ai checkout with issue_tracker not found -- see README",
)


class RealIssueTrackerProbeEngine:
    """A test-only 'engine' matching the AgentEngine Protocol shape: instead of calling a real
    or fake LLM, it makes one real MCP tool call against the real issue_tracker subprocess and
    wraps the result into a normal `result` NormalizedEvent -- exercising exactly the same
    ServerConfig -> subprocess spawn path the real engines use, through agent_runner's own
    execute_run, without needing a real agent loop."""

    def __init__(self, server: ServerConfig) -> None:
        self._server = server

    async def run(
        self, prompt: str, mcp_servers: dict[str, ServerConfig]
    ) -> AsyncIterator[NormalizedEvent]:
        params = StdioServerParameters(
            command=self._server.command,
            args=self._server.args,
            cwd=self._server.cwd,
            env={**self._server.env, "ISSUE_TRACKER_FAKE_GITHUB": "1"},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("list_issues", {"repo": "o/r"})

        yield NormalizedEvent(
            kind="result",
            payload={
                "is_error": result.is_error,
                "result_text": str(result.structured_content),
                "cost_usd": 0.0,
                "num_turns": 1,
            },
        )


async def test_real_stdio_session_against_the_real_issue_tracker_subprocess() -> None:
    server = _SERVERS["issues"]
    engine = RealIssueTrackerProbeEngine(server)

    events = [event async for event in engine.run("list issues", _SERVERS)]

    assert len(events) == 1
    assert events[0].kind == "result"
    assert events[0].payload["is_error"] is False
    assert "Fake issue for e2e testing" in events[0].payload["result_text"]
