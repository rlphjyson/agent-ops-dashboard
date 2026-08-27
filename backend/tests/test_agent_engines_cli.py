import asyncio
import json
import sys
from pathlib import Path

import pytest

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


def test_parse_line_extracts_the_system_init_event() -> None:
    events = [_parse_line(line) for line in _fixture_lines()]
    system_events = [e for e in events if e is not None and e.kind == "system"]
    assert len(system_events) == 1
    assert system_events[0].payload["tools"] == [
        "mcp__knowledge_base__create_note",
        "mcp__knowledge_base__get_backlinks",
        "mcp__knowledge_base__search_notes",
    ]


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
