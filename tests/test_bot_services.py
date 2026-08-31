import uuid
from datetime import UTC, datetime

import pytest

from app.bot.services import (
    DEFAULT_FILTER_KEYWORDS,
    DEFAULT_FILTER_VERSION,
    default_filter_values,
    default_filter_values_since,
    filters_confirmation_keyboard,
    filters_menu_keyboard,
    format_collected_message,
    format_filter_list,
    format_lead_notification,
    message_keyboard,
    parse_filter_command,
    parse_filter_values,
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


def test_filter_values_accept_newlines_and_both_comma_styles() -> None:
    parsed = parse_filter_values("Python developer\n.NET، تصميم مواقع,React")
    assert parsed == [
        ("Python developer", "python developer"),
        (".NET", ".net"),
        ("تصميم مواقع", "تصميم مواقع"),
        ("React", "react"),
    ]


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


def test_individual_filter_length_is_bounded_without_limiting_filter_count() -> None:
    with pytest.raises(ValueError, match="100"):
        parse_filter_command("add " + ("x" * 101))

    many_filters = parse_filter_values("\n".join(f"filter {index}" for index in range(75)))
    assert len(many_filters) == 75


def test_requested_default_filters_are_normalized_and_unique() -> None:
    defaults = default_filter_values()
    normalized = [item[1] for item in defaults]

    assert len(defaults) <= len(DEFAULT_FILTER_KEYWORDS)
    assert len(normalized) == len(set(normalized))
    assert ("مشروع", "مشروع") in defaults
    assert ("excel", "excel") in defaults
    assert ("سيره الذاتيه", "سيره الذاتيه") in defaults
    assert DEFAULT_FILTER_VERSION == 2


def test_existing_users_receive_only_new_default_filter_version() -> None:
    version_two = default_filter_values_since(1)
    normalized = {item[1] for item in version_two}

    assert "يسويلي" in normalized
    assert "مين يسوي" in normalized
    assert "بحث" not in normalized


def test_filter_list_display_is_bounded_without_dropping_saved_values() -> None:
    rendered = format_filter_list([f"filter {index}" for index in range(500)], max_characters=200)
    assert len(rendered) < 250
    assert "فلتر آخر" in rendered


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


def test_filter_keyboards_expose_add_confirm_and_cancel_actions() -> None:
    menu = filters_menu_keyboard()
    confirmation = filters_confirmation_keyboard()

    assert menu.inline_keyboard[0][0].callback_data == "filters:add:start"
    assert confirmation.inline_keyboard[0][0].callback_data == "filters:add:confirm"
    assert confirmation.inline_keyboard[0][1].callback_data == "filters:add:cancel"


def test_lead_notification_contains_required_sender_and_repeat_details() -> None:
    message = CollectedMessage(
        id=uuid.uuid4(),
        telegram_group_id=uuid.uuid4(),
        telegram_message_id=11,
        sender_telegram_id=123456789,
        sender_name="حنان",
        sender_username="username",
        text="مين يسوي ارقام سعودي واتس",
        normalized_text="مين يسوي ارقام سعودي واتس",
        message_date=datetime(2026, 8, 31, 15, 25, tzinfo=UTC),
        collected_at=datetime(2026, 8, 31, 15, 25, 1, tzinfo=UTC),
        source_account_id=uuid.uuid4(),
        content_hash="a" * 64,
        text_fingerprint="b" * 64,
    )
    message.group = TelegramGroup(
        id=message.telegram_group_id,
        telegram_chat_id=-100123,
        title="جامعة بيشه",
    )

    rendered = format_lead_notification(
        message,
        observer_names=["الحساب 1", "الحساب 2"],
        repeated_group_count=2,
        matched_keywords=("يسوي",),
        latency_ms=1250,
    )

    assert "🔔 طلب جديد" in rendered
    assert "🆔 User ID: 123456789" in rendered
    assert "📱 Username: @username" in rendered
    assert "📦 المجموعة: جامعة بيشه" in rendered
    assert "الحساب 1، الحساب 2" in rendered
    assert "كرر الطالب نفس الطلب في 2 مجموعات" in rendered
    assert "سبب الالتقاط: يسوي" in rendered
