"""Manual verification script (not a pytest test): runs the real, final CliAgentEngine against
the real mcp-toolkit-ai knowledge_base server, end to end. Run directly:
    .venv/Scripts/python.exe manual_verify_cli_engine.py
"""

import asyncio

from app.services import mcp_config
from app.services.agent_engines.cli import CliAgentEngine


async def main() -> None:
    toolkit_path = mcp_config.resolve_toolkit_path()
    servers = mcp_config.load_toolkit_servers(toolkit_path)
    kb_only = {"kb": servers["kb"]}

    engine = CliAgentEngine()
    async for event in engine.run(
        "Use the knowledge_base MCP tools to create a note titled 'Manual Verify' with content "
        "'created by agent-ops-dashboard's CliAgentEngine', then confirm it worked in one sentence.",
        kb_only,
    ):
        print(f"[{event.kind}] {event.payload}")


asyncio.run(main())
