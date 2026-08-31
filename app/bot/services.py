from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import CollectedMessage
from app.filtering import normalize_arabic

MAX_FILTERS_PER_USER = 20
MAX_FILTER_LENGTH = 100


@dataclass(frozen=True, slots=True)
class FilterCommand:
    action: str
    keywords: list[tuple[str, str]]


def parse_filter_command(arguments: str | None) -> FilterCommand:
    if not arguments or not arguments.strip():
        return FilterCommand(action="list", keywords=[])

    action, separator, raw_keywords = arguments.strip().partition(" ")
    action = action.casefold()
    if action == "clear" and not separator:
        return FilterCommand(action="clear", keywords=[])
    if action not in {"add", "remove"} or not raw_keywords.strip():
        raise ValueError(
            "استخدم /filters add كلمة، كلمة أخرى أو /filters remove كلمة أو /filters clear"
        )

    unique: dict[str, str] = {}
    for raw_keyword in raw_keywords.split(","):
        keyword = " ".join(raw_keyword.split())
        normalized = normalize_arabic(keyword)
        if not normalized:
            continue
        if len(keyword) > MAX_FILTER_LENGTH:
            raise ValueError(f"الفلتر يجب ألا يزيد عن {MAX_FILTER_LENGTH} حرفًا.")
        unique.setdefault(normalized, keyword)

    if not unique:
        raise ValueError("أضف كلمة أو عبارة واحدة على الأقل.")
    return FilterCommand(
        action=action,
        keywords=[(keyword, normalized) for normalized, keyword in unique.items()],
    )


def format_collected_message(message: CollectedMessage) -> str:
    text = message.text.strip() or "[رسالة بدون نص]"
    if len(text) > 2800:
        text = f"{text[:2797]}..."
    sender = message.sender_name or message.sender_username or "غير معروف"
    date = message.message_date.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return f"المجموعة: {message.group.title}\nالمرسل: {sender}\nالتاريخ: {date}\n\n{text}"


def message_keyboard(message: CollectedMessage, *, saved: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text="إزالة من المحفوظات" if saved else "حفظ",
            callback_data=("unsave:" if saved else "save:") + str(message.id),
        )
    ]
    if message.original_message_link:
        buttons.append(
            InlineKeyboardButton(text="فتح الرسالة الأصلية", url=message.original_message_link)
        )
    return InlineKeyboardMarkup(inline_keyboard=[buttons])
