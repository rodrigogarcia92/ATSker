"""Runtime configuration, read from the environment only.

Secrets are wrapped in `SecretStr` so that an accidental log line, traceback, or
error report prints `**********` instead of the value (PRD 10). Nothing here
raises when a variable is missing: local test runs import the app without a
database URL, and absence is reported through `/health` instead of a crash.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        # PowerShell writes .env with a BOM by default; without this the byte lands in
        # the first key and a secret can look present and be wrong. utf-8-sig strips a
        # BOM when there is one and reads plain UTF-8 unchanged when there is not.
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )

    env: str = "development"
    ui_default_lang: str = "es"

    database_url: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str | None = None
    # Decision 27: the providers' own defaults differ (DeepSeek high, Gemini
    # medium, GLM max) and running at one of them is a cost and latency variable
    # nobody chose — a one-page CV cost half an analysis budget that way. `low` is
    # the lowest effort all three candidates advertise; empty leaves the provider
    # default in place.
    openrouter_reasoning_effort: str | None = "low"
    session_secret: SecretStr | None = None

    @property
    def configured(self) -> dict[str, bool]:
        """Presence of each deployment secret, never its value."""
        return {
            "database_url": self.database_url is not None,
            "openrouter_api_key": self.openrouter_api_key is not None,
            "session_secret": self.session_secret is not None,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
