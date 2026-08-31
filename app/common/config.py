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
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: SecretStr
    bot_token: SecretStr | None = None
    bot_owner_telegram_id: int | None = None
    master_encryption_key: SecretStr | None = None
    log_level: str = "INFO"
    collector_queue_size: int = Field(default=1000, ge=1, le=100_000)
    db_pool_size: int = Field(default=5, ge=1, le=100)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    tg_api_id: int | None = None
    tg_api_hash: SecretStr | None = None
    tg_phone: SecretStr | None = None
    source_account_name: str | None = None

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

    def require_bot_owner_telegram_id(self) -> int:
        if self.bot_owner_telegram_id is None or self.bot_owner_telegram_id <= 0:
            raise RuntimeError("BOT_OWNER_TELEGRAM_ID is required by the bot worker")
        return self.bot_owner_telegram_id

    def require_encryption_key(self) -> str:
        if self.master_encryption_key is None or not self.master_encryption_key.get_secret_value():
            raise RuntimeError("MASTER_ENCRYPTION_KEY is required by the collector worker")
        return self.master_encryption_key.get_secret_value()

    def require_session_generation_values(self) -> tuple[int, str, str, str]:
        api_hash = self.tg_api_hash.get_secret_value() if self.tg_api_hash else ""
        phone = self.tg_phone.get_secret_value() if self.tg_phone else ""
        account_name = (self.source_account_name or "").strip()
        missing = [
            name
            for name, value in (
                ("TG_API_ID", self.tg_api_id),
                ("TG_API_HASH", api_hash),
                ("TG_PHONE", phone),
                ("SOURCE_ACCOUNT_NAME", account_name),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing session settings: {', '.join(missing)}")
        assert self.tg_api_id is not None
        return self.tg_api_id, api_hash, phone, account_name


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
