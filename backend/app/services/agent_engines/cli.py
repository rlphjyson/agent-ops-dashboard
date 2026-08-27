import asyncio
import json
import os
import platform
import shutil
import signal
import subprocess
import tempfile
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.services import mcp_config
from app.services.agent_engines.base import NormalizedEvent
from app.services.mcp_config import ServerConfig


def _kill_process_tree(pid: int) -> None:
    """Kills the process and everything it spawned, not just the immediate PID. Confirmed live:
    the `claude` CLI (npm package, Windows) is itself a thin wrapper that spawns a *child*
    claude.exe process inheriting a near-identical command line -- killing only the wrapper PID
    (what asyncio's Process object tracks) leaves that real child running as an orphan
    indefinitely, still burning real API cost, even though the run shows "cancelled" in the UI.
    Same class of bug, same fix, as this project's own Electron desktop wrapper teardown
    (taskkill /T /F, not a plain .kill()/process.kill()).

    subprocess.Popen here is fire-and-forget -- it only issues CreateProcess for taskkill itself
    and returns immediately, so this doesn't block the event loop it's called from despite being
    a synchronous call."""
    if platform.system() == "Windows":
        subprocess.Popen(  # noqa: S603, S607 -- fixed argv, no shell, no user input
            ["taskkill", "/pid", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        # Not verified live on this platform (this project's dev/target environment is
        # Windows) -- kills only the immediate process, which may have the same
        # orphaned-grandchild gap described above. getattr, not a bare signal.SIGKILL
        # reference: that attribute doesn't exist in the Windows signal module's type stubs,
        # which this project's mypy run always checks against regardless of the runtime branch.
        try:
            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        except ProcessLookupError:
            pass


class CliNotFoundError(Exception):
    pass


def _resolve_cli_path() -> str:
    settings = get_settings()
    if settings.claude_cli_path:
        return settings.claude_cli_path
    resolved = shutil.which("claude")
    if resolved is None:
        raise CliNotFoundError(
            "The `claude` CLI was not found on PATH. Install Claude Code, or set "
            "CLAUDE_CLI_PATH to its location."
        )
    return resolved


def to_cli_mcp_config(servers: dict[str, ServerConfig]) -> dict:
    """The --mcp-config JSON shape, confirmed via a real Phase 0 spike run. No "cwd" key --
    same as the SDK engine's mcp_servers shape, this format doesn't support one either (confirmed
    absent from the real captured spike output), so servers relying on a cwd-relative default
    (e.g. knowledge_base's ./vault) get an absolute env var override instead -- see
    mcp_config.resolve_env_for_cwdless_transport, shared with the SDK engine."""
    return {
        "mcpServers": {
            name: {
                "command": s.command,
                "args": s.args,
                "env": mcp_config.resolve_env_for_cwdless_transport(s),
            }
            for name, s in servers.items()
        }
    }


def _maybe_parse_json_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _extract_tool_result_content(result: Any) -> Any:
    """`tool_use_result` has (at least) two real, confirmed-by-live-testing shapes, not one --
    a first Phase 0 spike only exercised a list-returning tool (search_notes) and produced a
    dict {"content": <json str>, "structuredContent": {...}}; a later manual-verification run
    against a *dict*-returning tool (create_note) produced a plain list of content blocks
    instead ([{"type": "text", "text": <json str>}], with no structuredContent at all) -- the
    same underlying content-vs-structuredContent asymmetry already found in mcp-toolkit-ai's own
    servers this session, just surfacing differently at this layer. Handles both rather than
    assuming the one shape the first spike happened to produce."""
    if isinstance(result, dict):
        structured = result.get("structuredContent")
        if structured is not None:
            return structured
        return _maybe_parse_json_text(result.get("content"))
    if isinstance(result, list):
        texts = [
            block.get("text")
            for block in result
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        joined = "\n".join(t for t in texts if t is not None)
        return _maybe_parse_json_text(joined)
    return result


def _parse_line(line: str) -> NormalizedEvent | None:
    """Parses one line of `claude -p --output-format stream-json --verbose` output. Only the
    top-level assembled envelope types (system/assistant/user/result) are consumed -- confirmed
    via a real Phase 0 spike to be simpler and sufficient, versus hand-accumulating the raw
    stream_event content_block deltas (which remain available later for an optional token-by-
    token "typing" UI polish, not needed for correctness)."""
    try:
        obj: dict[str, Any] = json.loads(line)
    except json.JSONDecodeError:
        return None

    line_type = obj.get("type")

    if line_type == "system" and obj.get("subtype") == "init":
        # Every stream-json line carries session_id (confirmed against a real captured
        # transcript), including this one, the first line of any run -- capturing it here too
        # (not just from the final "result" line) is what lets a run *cancelled* mid-flight,
        # which never reaches a "result" event, still be resumed afterward via
        # POST /runs/{id}/messages. A real, live-caught bug: a cancelled run's session_id stayed
        # None and "continue the conversation" always failed with "no resumable session".
        return NormalizedEvent(
            kind="system",
            payload={"tools": obj.get("tools", []), "session_id": obj.get("session_id")},
        )

    if line_type == "assistant":
        for block in obj.get("message", {}).get("content", []):
            if block.get("type") == "tool_use":
                return NormalizedEvent(
                    kind="tool_use",
                    payload={
                        "tool_use_id": block["id"],
                        "name": block["name"],
                        "input": block.get("input", {}),
                    },
                )
            if block.get("type") == "text":
                return NormalizedEvent(
                    kind="assistant_text", payload={"text": block.get("text", "")}
                )
        return None

    if line_type == "user" and "tool_use_result" in obj:
        content_blocks = obj.get("message", {}).get("content", [])
        tool_use_id = content_blocks[0].get("tool_use_id") if content_blocks else None
        result = obj["tool_use_result"]
        return NormalizedEvent(
            kind="tool_result",
            payload={
                "tool_use_id": tool_use_id,
                "content": _extract_tool_result_content(result),
                "is_error": bool(result.get("is_error", False)) if isinstance(result, dict) else False,
            },
        )

    if line_type == "result":
        return NormalizedEvent(
            kind="result",
            payload={
                "is_error": obj.get("is_error", False),
                "result_text": obj.get("result") or "",
                "cost_usd": obj.get("total_cost_usd"),
                "num_turns": obj.get("num_turns"),
                # Every stream-json line carries this (confirmed against a real captured
                # transcript, not just the "system init" line) -- persisted so a later
                # POST /runs/{id}/messages can pass it back as --resume.
                "session_id": obj.get("session_id"),
            },
        )

    return None


class CliAgentEngine:
    """Runs a task by shelling out to the `claude` CLI in headless mode, reusing whatever Claude
    Code subscription login is already on this machine. Selected by
    agent_runner.default_agent_engine() when ANTHROPIC_API_KEY is unset.

    Confirmed via a real Phase 0 spike run: --tools "" --allowedTools "mcp__name__*" properly
    sandboxes the agent to only the declared MCP tools (no Claude Code built-ins leaked through),
    and the stream-json output's tool-result event shape is exactly what this parser expects.
    """

    async def run(
        self,
        prompt: str,
        mcp_servers: dict[str, ServerConfig],
        resume_session_id: str | None = None,
        register_killer: Callable[[Callable[[], None]], None] | None = None,
    ) -> AsyncIterator[NormalizedEvent]:
        settings = get_settings()
        cli_path = _resolve_cli_path()
        allowed_tools = ",".join(f"mcp__{name}__*" for name in mcp_servers)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as config_file:
            json.dump(to_cli_mcp_config(mcp_servers), config_file)
            config_path = config_file.name

        args = [
            cli_path,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--mcp-config",
            config_path,
            "--permission-mode",
            "dontAsk",
            "--tools",
            "",
            "--allowedTools",
            allowed_tools,
            "--max-budget-usd",
            str(settings.agent_max_budget_usd),
            "--max-turns",
            str(settings.agent_max_turns),
        ]
        if resume_session_id:
            args += ["--resume", resume_session_id]

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # asyncio's default StreamReader buffer is 64KB -- a single stream-json line can
                # easily exceed that (a system init event listing every tool across many MCP
                # servers, or a tool_result carrying real file/search content), which raises
                # LimitOverrunError ("Separator is found, but chunk is longer than limit") and
                # was crashing real runs. Confirmed live against a project with 19+ tools wired
                # in. 10MB comfortably covers any realistic single-line JSON event here.
                limit=10 * 1024 * 1024,
            )
            assert process.stdout is not None
            if register_killer is not None:
                register_killer(lambda: _kill_process_tree(process.pid))

            try:
                saw_result = False
                async for raw_line in process.stdout:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    event = _parse_line(line)
                    if event is not None:
                        if event.kind == "result":
                            saw_result = True
                        yield event

                stderr = (await process.stderr.read()) if process.stderr else b""
                returncode = await process.wait()
                if returncode != 0 and not saw_result:
                    # A `result` line (including a failed one) is itself a normal, already-
                    # surfaced outcome; only a *silent* non-zero exit (crashed before producing
                    # one) needs a synthetic error raised here for agent_runner to catch.
                    raise RuntimeError(
                        f"claude exited with code {returncode}: "
                        f"{stderr.decode('utf-8', errors='replace')[:2000]}"
                    )
            except asyncio.CancelledError:
                # Stopping a run cancels agent_runner's task while it's mid-await inside this
                # loop. register_killer's hook (above) has usually already killed the process
                # tree by now via run_registry -- this is a defensive fallback for direct
                # engine usage that never wired register_killer in the first place.
                # Deliberately NOT awaiting process.wait() here: confirmed live that calling
                # wait() a second time, after the process was already killed out-of-band by that
                # hook, hangs forever on this Windows environment (a real asyncio/
                # ProactorEventLoop subprocess-watcher quirk, not a bug in this code) rather than
                # returning once the process has, in fact, already exited. _kill_process_tree is
                # itself fire-and-forget (doesn't wait for taskkill), so this can't hang either.
                _kill_process_tree(process.pid)
                raise
        finally:
            Path(config_path).unlink(missing_ok=True)
