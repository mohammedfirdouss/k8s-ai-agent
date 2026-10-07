"""Application configuration.

Settings are loaded from environment variables (and a local `.env` file
if present) using pydantic-settings. See `.env.example` for the full list.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration for the service, loaded from the environment."""

    # AI provider (OpenRouter).
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = ""

    # Read-only kubectl tool calls the agent may make per investigation to
    # dig deeper than the collected evidence. 0 disables tool use.
    AGENT_MAX_TOOL_CALLS: int = 6

    # Path to the kubeconfig file used to talk to the cluster.
    KUBECONFIG_PATH: str = ""

    # InsForge project URL. When set, every API call (except /health) must
    # carry a valid InsForge user access token. Leave empty for local,
    # single-user mode with no login.
    INSFORGE_URL: str = ""
    # InsForge admin API key, used only server-side to write investigation
    # history on the user's behalf. Never expose it to the frontend.
    INSFORGE_API_KEY: str = ""

    # Comma-separated list of origins allowed to call this API.
    CORS_ORIGINS: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS_ORIGINS as a clean list of origin strings."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


# A single shared settings instance for the whole app.
settings = Settings()
