"""Application configuration.

Settings are loaded from environment variables (and a local `.env` file
if present) using pydantic-settings. See `.env.example` for the full list.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration for the service, loaded from the environment."""

    # AI provider (OpenRouter) — not used yet, wired up later.
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = ""

    # Path to the kubeconfig file used to talk to the cluster.
    KUBECONFIG_PATH: str = ""

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
