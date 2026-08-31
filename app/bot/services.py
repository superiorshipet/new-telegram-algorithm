from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import CollectedMessage
from app.filtering import normalize_arabic

MAX_FILTER_LENGTH = 100
_FILTER_SEPARATOR = re.compile(r"[,،\n]+")

DEFAULT_FILTER_KEYWORDS = (
    "يسوي",
    "تسوي",
    "بحث",
    "بحوث",
    "مشروع",
    "مشاريع",
    "واجب",
    "واجبات",
    "احتاج",
    "محتاج",
    "يحتاج",
    "تحتاج",
    "تعرفون",
    "يعرف",
    "يشرح",
    "تشرح",
    "فاهم",
    "يفهم",
    "خصوصي",
    "خاص",
    "مبرمج",
    "يبرمج",
    "يصمم",
    "مصمم",
    "يرسم",
    "برنامج",
    "يحل",
    "تحل",
    "يساعد",
    "تساعد",
    "مساعد",
    "خبرة",
    "اكسل",
    "excel",
    "يعدل",
    "تعدل",
    "يلخص",
    "تلخص",
    "تلخيص",
    "تفضل",
    "تفضلي",
    "ابشر",
    "ابشري",
    "ابي",
    "ابغى",
    "تقرير",
    "تقارير",
    "عرض",
    "برزنتيشن",
    "برزتيشن",
    "بريزنتيشن",
    "سيفي",
    "cv",
    "سيره ذاتيه",
    "سيره الذاتيه",
    "تكليف",
    "تكاليف",
    "فكره",
    "افكار",
    "حد",
    "تعال",
    "تعالي",
    "عندي",
)


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

    return FilterCommand(action=action, keywords=parse_filter_values(raw_keywords))


def parse_filter_values(raw_keywords: str) -> list[tuple[str, str]]:
    unique: dict[str, str] = {}
    for raw_keyword in _FILTER_SEPARATOR.split(raw_keywords):
        keyword = " ".join(raw_keyword.split())
        normalized = normalize_arabic(keyword)
        if not normalized:
            continue
        if len(keyword) > MAX_FILTER_LENGTH:
            raise ValueError(f"الفلتر يجب ألا يزيد عن {MAX_FILTER_LENGTH} حرفًا.")
        unique.setdefault(normalized, keyword)

    if not unique:
        raise ValueError("أضف كلمة أو عبارة واحدة على الأقل.")
    return [(keyword, normalized) for normalized, keyword in unique.items()]


def default_filter_values() -> list[tuple[str, str]]:
    return [
        (keyword, normalize_arabic(keyword)) for keyword in DEFAULT_FILTER_KEYWORDS
    ]


def format_filter_list(
    keywords: list[str], *, max_characters: int = 3000
) -> str:
    lines: list[str] = []
    used_characters = 0
    for keyword in keywords:
        line = f"• {keyword}"
        if used_characters + len(line) + 1 > max_characters:
            break
        lines.append(line)
        used_characters += len(line) + 1

    remaining = len(keywords) - len(lines)
    if remaining:
        lines.append(f"… و{remaining} فلتر آخر")
    return "\n".join(lines)


def filters_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Add",
                    callback_data="filters:add:start",
                )
            ]
        ]
    )


def filters_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Add",
                    callback_data="filters:add:confirm",
                ),
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="filters:add:cancel",
                ),
            ]
        ]
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
