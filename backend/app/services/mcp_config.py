import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings

CONFIG_FILENAME = "servers.toml"
ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ToolkitNotFoundError(Exception):
    """The sibling mcp-toolkit-ai checkout couldn't be found -- raised at app startup so this
    fails loudly and immediately, not silently on the first run a user happens to submit."""


@dataclass
class ServerConfig:
    name: str
    description: str
    command: str  # already resolved to an absolute interpreter path, not the "python" alias
    args: list[str]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)


def _expand_env_vars(value: str) -> str:
    """Expands ${VAR_NAME} references against this app's own environment -- same convention
    mcp-toolkit-ai's own CLI uses, so servers.toml doesn't need to change to work with either
    client."""

    def replace(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), "")

    return ENV_VAR_PATTERN.sub(replace, value)


def resolve_toolkit_path() -> Path:
    settings = get_settings()
    if settings.mcp_toolkit_path:
        candidate = Path(settings.mcp_toolkit_path).resolve()
    else:
        # This developer's own sibling-checkout convenience default -- documented in the README
        # as "works out of the box if you clone both repos next to each other."
        # mcp_config.py -> services -> app -> backend -> agent-ops-dashboard (repo root) ->
        # parents/siblings directory. parents[3] is the repo root itself, so the sibling
        # checkout is one level further up -- parents[4], not parents[3] (caught by the real
        # cross-repo e2e test resolving to a nonexistent .../agent-ops-dashboard/mcp-toolkit-ai
        # instead of the actual sibling, exactly the kind of mistake that test exists to catch).
        candidate = (Path(__file__).resolve().parents[4] / "mcp-toolkit-ai").resolve()

    if not (candidate / CONFIG_FILENAME).is_file():
        raise ToolkitNotFoundError(
            f"mcp-toolkit-ai checkout not found at {candidate} (no {CONFIG_FILENAME} there). "
            "Clone it as a sibling directory next to agent-ops-dashboard, or set "
            "MCP_TOOLKIT_PATH to your checkout. See README."
        )
    return candidate


def _resolve_toolkit_python(toolkit_path: Path) -> str:
    settings = get_settings()
    if settings.mcp_toolkit_venv_python:
        return settings.mcp_toolkit_venv_python
    for candidate in (
        toolkit_path / ".venv" / "Scripts" / "python.exe",  # Windows
        toolkit_path / ".venv" / "bin" / "python",  # POSIX
    ):
        if candidate.is_file():
            return str(candidate)
    raise ToolkitNotFoundError(
        f"No .venv found under {toolkit_path}. Install mcp-toolkit-ai's servers into a "
        "'.venv' there (see its README), or set MCP_TOOLKIT_VENV_PYTHON to the interpreter "
        "that has them installed."
    )


# Both real transports this app drives lack a "cwd" field entirely: the Agent SDK's
# McpStdioServerConfig TypedDict has no cwd key, and the `claude` CLI's --mcp-config JSON schema
# doesn't expose one either (both confirmed directly -- the SDK via mypy against the installed
# package's real type stubs, the CLI via a real Phase 0 spike's captured output -- contradicting
# an earlier, wrong assumption that the SDK's shape included cwd). A server that resolves a
# relative-path default against its own working directory would instead resolve it against
# whatever cwd the subprocess actually inherits (this backend's own directory) if nothing
# corrects for it -- so force an absolute override for exactly the servers/vars known to need
# one, unless servers.toml already provides an explicit override.
_CWD_RELATIVE_ENV_VARS: dict[str, str] = {
    "codebase": "CODEBASE_INTELLIGENCE_DATA_DIR",
    "sql": "SQL_QUERY_DATABASE_URL",
    "devenv": "DEV_ENVIRONMENT_LOG_DIR",
    "kb": "KNOWLEDGE_BASE_VAULT_DIR",
}


def resolve_env_for_cwdless_transport(server: ServerConfig) -> dict[str, str]:
    env = dict(server.env)
    env_var = _CWD_RELATIVE_ENV_VARS.get(server.name)
    if env_var is None or env_var in env:
        return env

    if server.name == "sql":
        env[env_var] = f"sqlite:///{(server.cwd / 'data' / 'sample.db').as_posix()}"
    elif server.name == "codebase":
        env[env_var] = str(server.cwd / "data")
    elif server.name == "devenv":
        env[env_var] = str(server.cwd / "logs")
    elif server.name == "kb":
        env[env_var] = str(server.cwd / "vault")
    return env


def load_toolkit_servers(toolkit_path: Path) -> dict[str, ServerConfig]:
    config_path = toolkit_path / CONFIG_FILENAME
    data = tomllib.loads(config_path.read_text())
    toolkit_python = _resolve_toolkit_python(toolkit_path)

    servers = {}
    for name, entry in data.get("servers", {}).items():
        command = entry["command"]
        servers[name] = ServerConfig(
            name=name,
            description=entry["description"],
            command=toolkit_python if command == "python" else command,
            args=entry.get("args", []),
            cwd=(toolkit_path / entry["cwd"]).resolve(),
            env={k: _expand_env_vars(v) for k, v in entry.get("env", {}).items()},
        )
    return servers
