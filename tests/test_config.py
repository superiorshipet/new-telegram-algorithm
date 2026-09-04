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
    with pytest.raises(RuntimeError, match="BOT_ACCESS_PASSWORD"):
        settings.require_bot_access_password()
    with pytest.raises(RuntimeError, match="MASTER_ENCRYPTION_KEY"):
        settings.require_encryption_key()
    with pytest.raises(RuntimeError, match="TG_API_ID"):
        settings.require_session_generation_values()
    with pytest.raises(RuntimeError, match="TG_API_ID"):
        settings.require_telegram_api_values()


def test_telegram_api_hash_must_be_exactly_32_hex_characters() -> None:
    settings = Settings(
        database_url="postgresql://user:pass@db/app",
        tg_api_id=12345,
        tg_api_hash="a" * 31,
        _env_file=None,
    )

    with pytest.raises(RuntimeError, match="exactly 32 hexadecimal characters"):
        settings.require_telegram_api_values()


def test_valid_telegram_api_values_are_returned() -> None:
    api_hash = "0123456789abcdef0123456789abcdef"
    settings = Settings(
        database_url="postgresql://user:pass@db/app",
        tg_api_id=12345,
        tg_api_hash=api_hash,
        _env_file=None,
    )

    assert settings.require_telegram_api_values() == (12345, api_hash)


def test_bot_access_password_is_loaded_as_a_secret() -> None:
    settings = Settings(
        database_url="postgresql://user:pass@db/app",
        bot_access_password="strong-test-password",
        _env_file=None,
    )

    assert settings.require_bot_access_password() == "strong-test-password"


def test_latency_worker_concurrency_has_safe_defaults() -> None:
    settings = Settings(database_url="postgresql://user:pass@db/app", _env_file=None)

    assert settings.collector_writer_concurrency == 4
    assert settings.notification_dispatch_concurrency == 8


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("collector_writer_concurrency", 0),
        ("notification_dispatch_concurrency", 33),
    ],
)
def test_latency_worker_concurrency_is_bounded(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql://user:pass@db/app",
            _env_file=None,
            **{field: value},
        )
