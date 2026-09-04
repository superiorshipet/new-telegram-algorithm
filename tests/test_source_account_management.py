import uuid
from unittest.mock import AsyncMock

from cryptography.fernet import Fernet

from app.bot.handlers.accounts import (
    accounts_list_keyboard,
    build_qr_png,
    create_accounts_router,
    format_accounts,
    login_method_keyboard,
    mask_phone,
)
from app.common.crypto import SecretCipher
from app.database.models import SourceAccount
from app.database.repositories import MAX_ACTIVE_SOURCE_ACCOUNTS
from app.database.repositories.source_accounts import SourceAccountRepository


def source_account(name: str, *, active: bool, status: str) -> SourceAccount:
    return SourceAccount(
        id=uuid.uuid4(),
        name=name,
        phone_number_masked="********1234",
        session_string_encrypted="encrypted-session",
        api_id_encrypted="encrypted-api-id",
        api_hash_encrypted="encrypted-api-hash",
        is_active=active,
        status=status,
    )


def test_phone_mask_preserves_only_last_four_digits() -> None:
    assert mask_phone("+966512341234") == "*********1234"
    assert mask_phone(None) is None


def test_login_menu_offers_qr_and_phone_methods() -> None:
    keyboard = login_method_keyboard()
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert "accounts:login:qr" in callbacks
    assert "accounts:login:phone" in callbacks


def test_account_list_exposes_start_and_stop_actions() -> None:
    active = source_account("الحساب 1", active=True, status="connected")
    disabled = source_account("الحساب 2", active=False, status="disabled")
    keyboard = accounts_list_keyboard([active, disabled])
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert f"accounts:disable:{active.id}" in callbacks
    assert f"accounts:enable:{disabled.id}" in callbacks


def test_account_summary_displays_active_limit_and_status() -> None:
    rendered = format_accounts(
        [
            source_account("الحساب 1", active=True, status="connected"),
            source_account("الحساب 2", active=False, status="disabled"),
        ]
    )

    assert f"1/{MAX_ACTIVE_SOURCE_ACCOUNTS}" in rendered
    assert "الحساب 1 — يعمل — الحالة: connected" in rendered
    assert "الحساب 2 — متوقف — الحالة: disabled" in rendered


def test_qr_login_image_is_a_png() -> None:
    image = build_qr_png("tg://login?token=test-token")

    assert image.startswith(b"\x89PNG\r\n\x1a\n")


def test_accounts_router_registers_management_flow() -> None:
    router = create_accounts_router(
        AsyncMock(),
        owner_telegram_id=123,
        cipher=SecretCipher(Fernet.generate_key().decode("ascii")),
        api_id=456,
        api_hash="a" * 32,
    )

    assert router.name == "source-accounts"
    assert router.shutdown.handlers


async def test_enabling_account_respects_active_account_limit() -> None:
    account = source_account("الحساب 4", active=False, status="disabled")
    session = AsyncMock()
    session.get.return_value = account
    session.scalar.return_value = MAX_ACTIVE_SOURCE_ACCOUNTS

    result = await SourceAccountRepository(session).set_active(account.id, active=True)

    assert result == "limit_reached"
    assert account.is_active is False
    assert account.status == "disabled"


async def test_disabling_account_marks_it_for_collector_reconciliation() -> None:
    account = source_account("الحساب 1", active=True, status="connected")
    session = AsyncMock()
    session.get.return_value = account

    result = await SourceAccountRepository(session).set_active(account.id, active=False)

    assert result == "updated"
    assert account.is_active is False
    assert account.status == "disabled"
