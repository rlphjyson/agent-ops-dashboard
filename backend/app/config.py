from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret_key: str = "dev-secret-change-me-please-32-bytes-min"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    database_url: str = "sqlite:///./data/agent_ops.db"
    cors_origins: str = "http://localhost:3000"

    # Engine selection is auto-detected from whether this is set (see services/agent_runner.py) --
    # not a separate on/off flag, so there's nothing to keep in sync with it.
    anthropic_api_key: str = ""
    # Overrides the shutil.which("claude") lookup the CLI engine otherwise does on its own.
    claude_cli_path: str = ""
    # Runaway-task guards, confirmed as real CliAgentEngine flags via a Phase 0 spike
    # (--max-budget-usd/--max-turns). Not yet wired into SdkAgentEngine -- no confirmed
    # ClaudeAgentOptions field for this found during Phase 0; open follow-up, not guessed at.
    agent_max_budget_usd: float = 5.0
    agent_max_turns: int = 20

    # Where the sibling mcp-toolkit-ai checkout lives. Empty means "fall back to
    # <this-repo>/../mcp-toolkit-ai" -- see services/mcp_config.py.
    mcp_toolkit_path: str = ""
    # Overrides the <mcp_toolkit_path>/.venv/{Scripts,bin}/python(.exe) convention lookup for the
    # interpreter that has mcp-toolkit-ai's servers installed (servers.toml's command="python").
    mcp_toolkit_venv_python: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
