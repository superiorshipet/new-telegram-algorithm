import uuid
from datetime import UTC, datetime

import pytest

from app.bot.services import (
    MAX_FILTERS_PER_USER,
    format_collected_message,
    message_keyboard,
    parse_filter_command,
)
from app.database.models import CollectedMessage, TelegramGroup


def test_empty_filter_command_lists_current_filters() -> None:
    parsed = parse_filter_command(None)
    assert parsed.action == "list"
    assert parsed.keywords == []


def test_add_filter_command_normalizes_and_deduplicates_keywords() -> None:
    parsed = parse_filter_command("add  Python,  إِعْلَان, python ")
    assert parsed.action == "add"
    assert parsed.keywords == [("Python", "python"), ("إِعْلَان", "اعلان")]


def test_remove_and_clear_filter_commands_are_supported() -> None:
    remove = parse_filter_command("remove .NET, تصميم مواقع")
    clear = parse_filter_command("clear")
    assert remove.action == "remove"
    assert remove.keywords == [(".NET", ".net"), ("تصميم مواقع", "تصميم مواقع")]
    assert clear.action == "clear"


@pytest.mark.parametrize("arguments", ["add", "remove", "unknown keyword", "clear now"])
def test_invalid_filter_commands_return_a_useful_error(arguments: str) -> None:
    with pytest.raises(ValueError, match="/filters"):
        parse_filter_command(arguments)


def test_filter_length_is_bounded() -> None:
    with pytest.raises(ValueError, match="100"):
        parse_filter_command("add " + ("x" * 101))
    assert MAX_FILTERS_PER_USER == 20


def test_message_format_and_buttons_include_expected_actions() -> None:
    message = CollectedMessage(
        id=uuid.uuid4(),
        telegram_group_id=uuid.uuid4(),
        telegram_message_id=10,
        text="مطلوب مطور Python",
        normalized_text="مطلوب مطور python",
        message_date=datetime(2026, 8, 31, 12, 30, tzinfo=UTC),
        source_account_id=uuid.uuid4(),
        content_hash="a" * 64,
        original_message_link="https://t.me/example/10",
    )
    message.group = TelegramGroup(
        id=message.telegram_group_id,
        telegram_chat_id=-100123,
        title="فرص العمل",
    )

    rendered = format_collected_message(message)
    latest_keyboard = message_keyboard(message)
    saved_keyboard = message_keyboard(message, saved=True)

    assert "فرص العمل" in rendered
    assert "مطلوب مطور Python" in rendered
    assert latest_keyboard.inline_keyboard[0][0].callback_data == f"save:{message.id}"
    assert saved_keyboard.inline_keyboard[0][0].callback_data == f"unsave:{message.id}"
