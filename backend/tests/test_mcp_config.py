from pathlib import Path

import pytest

from app.config import get_settings
from app.services import mcp_config
from app.services.mcp_config import ServerConfig, ToolkitNotFoundError


def _server(name: str, cwd: Path, env: dict[str, str] | None = None) -> ServerConfig:
    return ServerConfig(
        name=name, description="", command="python", args=[], cwd=cwd, env=env or {}
    )


def test_resolve_env_overrides_sql_server_default(tmp_path: Path) -> None:
    server = _server("sql", tmp_path)
    env = mcp_config.resolve_env_for_cwdless_transport(server)
    assert env["SQL_QUERY_DATABASE_URL"] == f"sqlite:///{(tmp_path / 'data' / 'sample.db').as_posix()}"


def test_resolve_env_overrides_codebase_server_default(tmp_path: Path) -> None:
    server = _server("codebase", tmp_path)
    env = mcp_config.resolve_env_for_cwdless_transport(server)
    assert env["CODEBASE_INTELLIGENCE_DATA_DIR"] == str(tmp_path / "data")


def test_resolve_env_overrides_devenv_server_default(tmp_path: Path) -> None:
    server = _server("devenv", tmp_path)
    env = mcp_config.resolve_env_for_cwdless_transport(server)
    assert env["DEV_ENVIRONMENT_LOG_DIR"] == str(tmp_path / "logs")


def test_resolve_env_overrides_kb_server_default(tmp_path: Path) -> None:
    server = _server("kb", tmp_path)
    env = mcp_config.resolve_env_for_cwdless_transport(server)
    assert env["KNOWLEDGE_BASE_VAULT_DIR"] == str(tmp_path / "vault")


def test_resolve_env_leaves_an_explicit_override_alone(tmp_path: Path) -> None:
    server = _server("kb", tmp_path, env={"KNOWLEDGE_BASE_VAULT_DIR": "/explicit/path"})
    env = mcp_config.resolve_env_for_cwdless_transport(server)
    assert env["KNOWLEDGE_BASE_VAULT_DIR"] == "/explicit/path"


def test_resolve_env_is_a_no_op_for_a_server_with_no_known_cwd_relative_var(tmp_path: Path) -> None:
    server = _server("issues", tmp_path, env={"GITHUB_TOKEN": "x"})
    env = mcp_config.resolve_env_for_cwdless_transport(server)
    assert env == {"GITHUB_TOKEN": "x"}


def test_resolve_toolkit_path_raises_a_clear_error_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("MCP_TOOLKIT_PATH", str(tmp_path / "does-not-exist"))
    try:
        with pytest.raises(ToolkitNotFoundError, match="Clone it as a sibling directory"):
            mcp_config.resolve_toolkit_path()
    finally:
        get_settings.cache_clear()


def test_resolve_toolkit_path_returns_it_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "servers.toml").write_text("")
    get_settings.cache_clear()
    monkeypatch.setenv("MCP_TOOLKIT_PATH", str(tmp_path))
    try:
        assert mcp_config.resolve_toolkit_path() == tmp_path.resolve()
    finally:
        get_settings.cache_clear()


def test_load_toolkit_servers_resolves_python_command_and_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.touch()

    (tmp_path / "servers.toml").write_text(
        """
[servers.kb]
description = "knowledge base"
command = "python"
args = ["-m", "knowledge_base.server"]
cwd = "servers/knowledge_base"
"""
    )

    servers = mcp_config.load_toolkit_servers(tmp_path)

    assert servers["kb"].command == str(venv_python)
    assert servers["kb"].args == ["-m", "knowledge_base.server"]
    assert servers["kb"].cwd == (tmp_path / "servers" / "knowledge_base").resolve()


def test_load_toolkit_servers_expands_env_vars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.touch()
    monkeypatch.setenv("MY_TEST_TOKEN", "secret-value")

    (tmp_path / "servers.toml").write_text(
        """
[servers.issues]
description = "issues"
command = "python"
args = ["-m", "issue_tracker.server"]
cwd = "servers/issue_tracker"

[servers.issues.env]
GITHUB_TOKEN = "${MY_TEST_TOKEN}"
"""
    )

    servers = mcp_config.load_toolkit_servers(tmp_path)

    assert servers["issues"].env == {"GITHUB_TOKEN": "secret-value"}
