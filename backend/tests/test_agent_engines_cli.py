import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from app.services.agent_engines import cli as cli_module
from app.services.agent_engines.cli import _parse_line, to_cli_mcp_config
from app.services.mcp_config import ServerConfig

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "cli_stream_sample.jsonl"
DICT_RETURN_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "cli_stream_sample_dict_return.jsonl"


def _fixture_lines(path: Path = FIXTURE_PATH) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_fixture_is_a_real_captured_transcript() -> None:
    # Sanity check on the fixture itself: this is a real `claude -p --output-format stream-json`
    # transcript captured during the Phase 0 spike (see the plan file), not hand-written --
    # confirms the parser tests below are grounded in real output, not an assumed shape.
    lines = _fixture_lines()
    assert len(lines) == 30
    assert all(json.loads(line) for line in lines)


def test_parse_line_extracts_the_tool_use_event() -> None:
    events = [_parse_line(line) for line in _fixture_lines()]
    tool_use_events = [e for e in events if e is not None and e.kind == "tool_use"]
    assert len(tool_use_events) == 1
    assert tool_use_events[0].payload == {
        "tool_use_id": "toolu_01LHhgiauVP8zSaQZhsh2pZV",
        "name": "mcp__knowledge_base__search_notes",
        "input": {"query": "banana42"},
    }


def test_parse_line_extracts_the_tool_result_event_with_structured_content() -> None:
    events = [_parse_line(line) for line in _fixture_lines()]
    tool_result_events = [e for e in events if e is not None and e.kind == "tool_result"]
    assert len(tool_result_events) == 1
    result = tool_result_events[0].payload
    assert result["tool_use_id"] == "toolu_01LHhgiauVP8zSaQZhsh2pZV"
    assert result["is_error"] is False
    # structuredContent (the already-parsed shape) is preferred over the raw JSON-text content.
    assert result["content"] == {"result": [{"path": "test.md", "title": "Test Note"}]}


def test_parse_line_extracts_assistant_text_events() -> None:
    events = [_parse_line(line) for line in _fixture_lines()]
    text_events = [e for e in events if e is not None and e.kind == "assistant_text"]
    assert any("banana42" in e.payload["text"] for e in text_events)


def test_parse_line_extracts_the_final_result_event() -> None:
    events = [_parse_line(line) for line in _fixture_lines()]
    result_events = [e for e in events if e is not None and e.kind == "result"]
    assert len(result_events) == 1
    payload = result_events[0].payload
    assert payload["is_error"] is False
    assert payload["num_turns"] == 2
    assert payload["cost_usd"] == 0.046294800000000004
    assert "Test Note" in payload["result_text"]
    assert payload["session_id"] == "297011a2-64d1-42ef-8322-5714634c6c58"


def test_parse_line_extracts_the_system_init_event() -> None:
    events = [_parse_line(line) for line in _fixture_lines()]
    system_events = [e for e in events if e is not None and e.kind == "system"]
    assert len(system_events) == 1
    assert system_events[0].payload["tools"] == [
        "mcp__knowledge_base__create_note",
        "mcp__knowledge_base__get_backlinks",
        "mcp__knowledge_base__search_notes",
    ]
    # Captured here too, not just on the final "result" line -- a run cancelled before ever
    # reaching a result event still needs a resumable session_id.
    assert system_events[0].payload["session_id"] == "297011a2-64d1-42ef-8322-5714634c6c58"


def test_parse_line_skips_stream_event_and_rate_limit_lines() -> None:
    # These carry the raw per-token deltas -- not needed for correctness (see Phase 0 findings),
    # so the parser deliberately returns None for them rather than trying to reassemble text
    # from partial_json/text deltas that the top-level assistant/user/result lines already give
    # fully assembled.
    events = [_parse_line(line) for line in _fixture_lines()]
    non_none_kinds = {e.kind for e in events if e is not None}
    assert non_none_kinds == {"system", "assistant_text", "tool_use", "tool_result", "result"}


def test_parse_line_returns_none_for_malformed_json() -> None:
    assert _parse_line("not json at all") is None


def test_parse_line_extracts_tool_result_content_for_a_dict_returning_tool() -> None:
    # Regression test for a real bug caught during manual verification: a *dict*-returning tool
    # (create_note) produces a tool_use_result shaped as a plain list of content blocks, not the
    # {"content", "structuredContent"} dict shape a list-returning tool (search_notes) produces --
    # the parser originally only handled the dict shape and silently returned content=None here.
    events = [_parse_line(line) for line in _fixture_lines(DICT_RETURN_FIXTURE_PATH)]
    tool_result_events = [e for e in events if e is not None and e.kind == "tool_result"]
    assert len(tool_result_events) == 1
    content = tool_result_events[0].payload["content"]
    assert content["title"] == "Debug Verify"
    # Exact filename isn't asserted: knowledge_base's create_note de-duplicates on collision
    # (debug-verify.md, debug-verify-2.md, ...), and this fixture was captured by re-running the
    # same debug script against the same vault more than once.
    assert content["path"].startswith("debug-verify")


def test_kill_process_tree_uses_taskkill_with_tree_and_force_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression test for a real, live-caught bug: the `claude` CLI (npm package, Windows) spawns
    # a *child* claude.exe process inheriting a near-identical command line. A plain
    # process.kill() only terminates the immediate wrapper PID, leaving that real child running
    # indefinitely as an orphan (confirmed live: still burning real API cost minutes later, even
    # though the run showed "cancelled"). /T /F is what actually kills the whole tree -- the same
    # fix already used for this project's own Electron desktop wrapper teardown.
    captured: dict[str, object] = {}

    def _fake_popen(args, **kwargs):
        captured["args"] = args
        captured["stdout"] = kwargs.get("stdout")
        captured["stderr"] = kwargs.get("stderr")

    monkeypatch.setattr(cli_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(cli_module.subprocess, "Popen", _fake_popen)

    cli_module._kill_process_tree(4242)

    assert captured["args"] == ["taskkill", "/pid", "4242", "/T", "/F"]
    assert captured["stdout"] is cli_module.subprocess.DEVNULL
    assert captured["stderr"] is cli_module.subprocess.DEVNULL


def test_to_cli_mcp_config_shape(tmp_path: Path) -> None:
    # Use a real tmp_path rather than a hardcoded Windows-style string so this test is correct on
    # any host OS -- Path's own separator, not an assumed one.
    server_cwd = tmp_path / "toolkit" / "servers" / "knowledge_base"
    servers = {
        "kb": ServerConfig(
            name="kb",
            description="knowledge base",
            command=str(tmp_path / "venv" / "python"),
            args=["-m", "knowledge_base.server"],
            cwd=server_cwd,
            env={},
        )
    }

    config = to_cli_mcp_config(servers)

    assert config == {
        "mcpServers": {
            "kb": {
                "command": str(tmp_path / "venv" / "python"),
                "args": ["-m", "knowledge_base.server"],
                "env": {"KNOWLEDGE_BASE_VAULT_DIR": str(server_cwd / "vault")},
            }
        }
    }


_PRINT_A_100K_CHAR_LINE = 'print("x" * 100_000)'  # generated inside the subprocess, not passed
# as a literal argument -- a 100K-char string embedded directly in the command line itself hits
# Windows' own CreateProcess argument-length limit ("filename or extension is too long"),
# a different and unrelated limit from the asyncio StreamReader one this test actually targets.


async def test_reading_stdout_does_not_raise_on_a_line_over_64kb() -> None:
    # Regression test for a real, live-caught bug: asyncio's default StreamReader buffer is 64KB,
    # and a single stream-json line (e.g. a system init event listing every tool across several
    # MCP servers) can exceed that -- confirmed live against a project wired up with 19 tools,
    # which crashed every run with a ValueError from asyncio's stream-limit check ("Separator is
    # found, but chunk is longer than limit" / "Separator is not found, and chunk exceed the
    # limit", depending on exactly where the overrun is detected). CliAgentEngine.run passes
    # limit=10MB to create_subprocess_exec to fix this; this test exercises that exact mechanic
    # (a real subprocess emitting an oversized line, read the same way CliAgentEngine reads it)
    # without needing the real claude binary.
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _PRINT_A_100K_CHAR_LINE,
        stdout=asyncio.subprocess.PIPE,
        limit=10 * 1024 * 1024,
    )
    assert process.stdout is not None

    lines = []
    async for raw_line in process.stdout:
        lines.append(raw_line.decode("utf-8").strip())
    await process.wait()

    assert lines == ["x" * 100_000]


async def test_reading_stdout_without_the_limit_fix_reproduces_the_real_bug() -> None:
    # The other half of the regression: confirms the failure mode itself is real (not a made-up
    # concern) by reproducing it with the default 64KB limit -- if this stops raising on some
    # future Python/asyncio version, the fix above may no longer be necessary, which is exactly
    # the kind of drift this test would catch.
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _PRINT_A_100K_CHAR_LINE,
        stdout=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None

    with pytest.raises(ValueError, match="chunk"):
        async for _ in process.stdout:
            pass
    await process.wait()


class _EmptyStdout:
    def __aiter__(self) -> "_EmptyStdout":
        return self

    async def __anext__(self) -> bytes:
        raise StopAsyncIteration


class _EmptyProcess:
    stdout = _EmptyStdout()
    stderr = None
    returncode = 0
    pid = 111

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return 0


class _HangingStdout:
    def __aiter__(self) -> "_HangingStdout":
        return self

    async def __anext__(self) -> bytes:
        # Simulates a still-running process that hasn't produced its next line yet -- blocks
        # forever so a test can cancel the surrounding task while genuinely mid-await here,
        # exactly where a real Stop request would interrupt a real subprocess read.
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class _HangingProcess:
    def __init__(self) -> None:
        self.stdout = _HangingStdout()
        self.stderr = None
        self.returncode: int | None = None
        self.pid = 222

    async def wait(self) -> int:
        assert self.returncode is not None
        return self.returncode


async def test_run_passes_the_resume_flag_when_a_session_id_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, tuple] = {}

    async def _fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        return _EmptyProcess()

    monkeypatch.setattr(cli_module, "_resolve_cli_path", lambda: "claude")
    monkeypatch.setattr(cli_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    engine = cli_module.CliAgentEngine()
    events = [e async for e in engine.run("hi", {}, resume_session_id="sess-xyz")]

    assert events == []
    args = captured["args"]
    assert "--resume" in args
    assert args[args.index("--resume") + 1] == "sess-xyz"


async def test_run_omits_the_resume_flag_for_a_fresh_run(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, tuple] = {}

    async def _fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        return _EmptyProcess()

    monkeypatch.setattr(cli_module, "_resolve_cli_path", lambda: "claude")
    monkeypatch.setattr(cli_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    engine = cli_module.CliAgentEngine()
    [e async for e in engine.run("hi", {})]

    assert "--resume" not in captured["args"]


async def test_run_registers_a_tree_killer_as_the_kill_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    # register_killer is what lets run_registry.cancel() kill the real subprocess directly,
    # instead of relying solely on task cancellation -- confirmed live to not promptly interrupt
    # a pending stdout read on Windows (see run_registry's module docstring). It's registered as
    # a call into _kill_process_tree, not a bare process.kill: confirmed live that the `claude`
    # CLI spawns a *child* claude.exe process that survives killing only the immediate PID.
    fake_process = _EmptyProcess()
    killed_pids: list[int] = []

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return fake_process

    monkeypatch.setattr(cli_module, "_resolve_cli_path", lambda: "claude")
    monkeypatch.setattr(cli_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    monkeypatch.setattr(cli_module, "_kill_process_tree", killed_pids.append)

    registered: list[Callable[[], None]] = []
    engine = cli_module.CliAgentEngine()
    [e async for e in engine.run("hi", {}, register_killer=registered.append)]

    assert len(registered) == 1
    registered[0]()
    assert killed_pids == [fake_process.pid]


async def test_run_kills_the_subprocess_tree_when_cancelled_mid_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression-style test for the same class of orphaned-process bug already found and fixed
    # once this session in the Electron desktop wrapper's own shutdown handling: stopping a run
    # must not leave the real `claude` subprocess (or its child) running in the background. This
    # exercises the fallback path -- no register_killer given, so CliAgentEngine's own
    # CancelledError handler is what has to call _kill_process_tree.
    fake_process = _HangingProcess()
    killed_pids: list[int] = []

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return fake_process

    monkeypatch.setattr(cli_module, "_resolve_cli_path", lambda: "claude")
    monkeypatch.setattr(cli_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    monkeypatch.setattr(cli_module, "_kill_process_tree", killed_pids.append)

    engine = cli_module.CliAgentEngine()

    async def _consume() -> None:
        async for _ in engine.run("hi", {}):
            pass

    task = asyncio.create_task(_consume())
    for _ in range(10):
        await asyncio.sleep(0)  # let it reach the hanging stdout await

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert killed_pids == [fake_process.pid]


class _NeverResolvingWait:
    """Simulates the exact real bug found live: a process whose wait() hangs forever once it's
    already been killed out-of-band (by register_killer's hook, called from run_registry before
    task.cancel() even reaches this generator) -- confirmed on this Windows environment to be a
    real asyncio subprocess-watcher quirk, not a hypothetical. The fix is that CliAgentEngine's
    CancelledError handler must never call `await process.wait()` at all; this class exists so a
    regression that reintroduces that call makes this test hang/timeout instead of silently
    passing."""

    def __init__(self) -> None:
        self.stdout = _HangingStdout()
        self.stderr = None
        self.returncode: int | None = None
        self.pid = 333

    async def wait(self) -> int:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


async def test_run_does_not_await_process_wait_again_after_cancelling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_process = _NeverResolvingWait()

    async def _fake_create_subprocess_exec(*args, **kwargs):
        return fake_process

    monkeypatch.setattr(cli_module, "_resolve_cli_path", lambda: "claude")
    monkeypatch.setattr(cli_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    monkeypatch.setattr(cli_module, "_kill_process_tree", lambda pid: None)

    engine = cli_module.CliAgentEngine()

    async def _consume() -> None:
        async for _ in engine.run("hi", {}):
            pass

    task = asyncio.create_task(_consume())
    for _ in range(10):
        await asyncio.sleep(0)

    task.cancel()
    # If CliAgentEngine ever calls `await process.wait()` again here, this hangs forever and the
    # test times out instead of completing -- that's deliberate, see the class docstring above.
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2)
