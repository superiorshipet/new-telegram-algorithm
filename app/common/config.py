from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(value: str) -> str:
    """Return a SQLAlchemy asyncpg URL without changing credentials."""
    stripped = value.strip()
    if stripped.startswith("postgresql+asyncpg://"):
        return stripped
    if stripped.startswith("postgresql://"):
        return stripped.replace("postgresql://", "postgresql+asyncpg://", 1)
    if stripped.startswith("postgres://"):
        return stripped.replace("postgres://", "postgresql+asyncpg://", 1)
    raise ValueError("DATABASE_URL must be a PostgreSQL connection URL")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    database_url: SecretStr
    bot_token: SecretStr | None = None
    master_encryption_key: SecretStr | None = None
    log_level: str = "INFO"
    collector_queue_size: int = Field(default=1000, ge=1, le=100_000)
    db_pool_size: int = Field(default=5, ge=1, le=100)
    db_max_overflow: int = Field(default=10, ge=0, le=100)

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("DATABASE_URL is required")  # noqa: TRY004
        return normalize_database_url(value)

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL is invalid")
        return normalized

    @property
    def sqlalchemy_database_url(self) -> str:
        return self.database_url.get_secret_value()

    def require_bot_token(self) -> str:
        if self.bot_token is None or not self.bot_token.get_secret_value():
            raise RuntimeError("BOT_TOKEN is required by the bot worker")
        return self.bot_token.get_secret_value()

    def require_encryption_key(self) -> str:
        if self.master_encryption_key is None or not self.master_encryption_key.get_secret_value():
            raise RuntimeError("MASTER_ENCRYPTION_KEY is required by the collector worker")
        return self.master_encryption_key.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
