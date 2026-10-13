"""App settings, read from environment variables (or a local .env file)."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Required. Reads ANTHROPIC_API_KEY. SecretStr keeps it out of logs and error messages.
    anthropic_api_key: SecretStr

    # Required. Reads PITCHR_AI_API_KEY: the shared secret NestJS must send with
    # every request. The same value is set in pitchr-server.
    pitchr_ai_api_key: SecretStr

    # Optional. Reads CLAUDE_MODEL, so the model can be changed without a code change.
    # Sonnet 5.5 matched Opus 5.5 on the lead snapshot evals at half the cost and
    # about 30% faster; Haiku 5.5 invented a fact (see docs/lead-snapshot-build-plan.md).
    claude_model: str = "claude-sonnet-5-5"


@lru_cache
def get_settings() -> Settings:
    """Load settings once and reuse them on every call."""
    return Settings()
