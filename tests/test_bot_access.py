import uuid

import pytest

from app.bot.handlers.registration import access_list_keyboard, access_role_keyboard
from app.database.models import BotAccessGrant
from app.database.repositories.bot_access import parse_access_subject


def test_access_subject_accepts_telegram_user_id() -> None:
    subject = parse_access_subject(" 123456789 ")

    assert subject.subject_type == "telegram_id"
    assert subject.subject_value == "123456789"
    assert subject.display == "123456789"


def test_access_subject_normalizes_username() -> None:
    subject = parse_access_subject(" @Shipet_004 ")

    assert subject.subject_type == "username"
    assert subject.subject_value == "shipet_004"
    assert subject.display == "@shipet_004"


@pytest.mark.parametrize("value", ["", "+201234567890", "username", "@bad-name"])
def test_access_subject_rejects_phone_numbers_and_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_access_subject(value)


def test_owner_can_choose_user_or_admin_role() -> None:
    keyboard = access_role_keyboard()

    assert keyboard.inline_keyboard[0][0].callback_data == "access:role:user"
    assert keyboard.inline_keyboard[0][1].callback_data == "access:role:admin"


def test_delegated_admin_cannot_receive_admin_revoke_button() -> None:
    regular = BotAccessGrant(
        id=uuid.uuid4(),
        subject_type="telegram_id",
        subject_value="100",
        granted_by_telegram_user_id=1,
        is_active=True,
        is_access_admin=False,
    )
    admin = BotAccessGrant(
        id=uuid.uuid4(),
        subject_type="telegram_id",
        subject_value="200",
        granted_by_telegram_user_id=1,
        is_active=True,
        is_access_admin=True,
    )

    keyboard = access_list_keyboard(
        [regular, admin],
        allow_admin_management=False,
    )
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert f"access:revoke:{regular.id}" in callbacks
    assert f"access:revoke:{admin.id}" not in callbacks
