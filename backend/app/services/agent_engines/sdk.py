from collections.abc import AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)
from claude_agent_sdk.types import McpServerConfig, McpStdioServerConfig

from app.services import mcp_config
from app.services.agent_engines.base import NormalizedEvent
from app.services.mcp_config import ServerConfig


def _to_agent_sdk_servers(servers: dict[str, ServerConfig]) -> dict[str, McpServerConfig]:
    # McpStdioServerConfig has no "cwd" field (confirmed against the installed package's real
    # type stubs, contradicting an earlier docs-based assumption that it did) -- see
    # mcp_config.resolve_env_for_cwdless_transport for why an absolute env override stands in
    # for it on the handful of servers that actually need one.
    return {
        name: McpStdioServerConfig(
            command=s.command,
            args=s.args,
            env=mcp_config.resolve_env_for_cwdless_transport(s),
        )
        for name, s in servers.items()
    }


class SdkAgentEngine:
    """Runs a task via the Claude Agent SDK, authenticated with ANTHROPIC_API_KEY (read from the
    environment by the SDK itself). Selected by agent_runner.default_agent_engine() only when
    that env var is set.

    Message-shape mapping confirmed via a real Phase 0 spike run + reading claude_agent_sdk's own
    type definitions directly, not assumed from docs.

    NOT YET VERIFIED: whether `allowed_tools` actually sandboxes the tool surface when running
    WITH a real API key (a real Phase 0 spike confirmed it does NOT when the SDK falls back to a
    key-less ambient subscription login instead -- that's a different code path, CliAgentEngine's,
    not this one, but this specific combination -- API key + allowed_tools -- hasn't been live-
    tested yet since no key was available during Phase 0). Verify with a real key before relying
    on this engine for anything beyond local dev; see the plan's Risk #0.
    """

    async def run(
        self, prompt: str, mcp_servers: dict[str, ServerConfig]
    ) -> AsyncIterator[NormalizedEvent]:
        options = ClaudeAgentOptions(
            mcp_servers=_to_agent_sdk_servers(mcp_servers),
            allowed_tools=[f"mcp__{name}__*" for name in mcp_servers],
        )

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, SystemMessage):
                if message.subtype == "init":
                    yield NormalizedEvent(
                        kind="system", payload={"tools": message.data.get("tools", [])}
                    )
                continue

            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        yield NormalizedEvent(
                            kind="tool_use",
                            payload={
                                "tool_use_id": block.id,
                                "name": block.name,
                                "input": block.input,
                            },
                        )
                    elif isinstance(block, TextBlock):
                        yield NormalizedEvent(kind="assistant_text", payload={"text": block.text})
                continue

            if isinstance(message, UserMessage):
                blocks = message.content if isinstance(message.content, list) else []
                for block in blocks:
                    if isinstance(block, ToolResultBlock):
                        yield NormalizedEvent(
                            kind="tool_result",
                            payload={
                                "tool_use_id": block.tool_use_id,
                                "content": block.content,
                                "is_error": bool(block.is_error),
                            },
                        )
                continue

            if isinstance(message, ResultMessage):
                yield NormalizedEvent(
                    kind="result",
                    payload={
                        "is_error": message.is_error,
                        "result_text": message.result or "",
                        "cost_usd": message.total_cost_usd,
                        "num_turns": message.num_turns,
                    },
                )
                continue

            # RateLimitEvent and any other message types are informational-only, skipped.
