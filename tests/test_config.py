import pytest
from pydantic import ValidationError

from app.common.config import Settings, normalize_database_url


def test_railway_postgresql_url_is_normalized_for_asyncpg() -> None:
    settings = Settings(database_url="postgresql://user:pass@db:5432/app", _env_file=None)
    assert settings.sqlalchemy_database_url == ("postgresql+asyncpg://user:pass@db:5432/app")


def test_already_async_url_is_unchanged() -> None:
    value = "postgresql+asyncpg://user:pass@db:5432/app"
    assert normalize_database_url(value) == value


def test_non_postgresql_database_is_rejected() -> None:
    with pytest.raises((ValidationError, ValueError)):
        Settings(database_url="sqlite:///local.db", _env_file=None)


def test_service_specific_secrets_are_optional_until_worker_start() -> None:
    settings = Settings(database_url="postgresql://user:pass@db/app", _env_file=None)
    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        settings.require_bot_token()
    with pytest.raises(RuntimeError, match="BOT_OWNER_TELEGRAM_ID"):
        settings.require_bot_owner_telegram_id()
    with pytest.raises(RuntimeError, match="MASTER_ENCRYPTION_KEY"):
        settings.require_encryption_key()
    with pytest.raises(RuntimeError, match="TG_API_ID"):
        settings.require_session_generation_values()
