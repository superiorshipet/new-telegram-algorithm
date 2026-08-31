from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import CollectedMessage
from app.filtering import normalize_arabic

MAX_FILTER_LENGTH = 100
_FILTER_SEPARATOR = re.compile(r"[,،\n]+")

DEFAULT_FILTER_KEYWORDS_V1 = (
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

DEFAULT_FILTER_KEYWORDS_V2 = (
    "يسويه",
    "يسويلي",
    "مشروعي",
    "من يعرف",
    "من يقدر",
    "مين يسوي",
    "خصوصيه",
    "يساعدني",
    "الاكسل",
    "سيرة ذاتيه",
    "يحله",
)

DEFAULT_FILTER_SETS = {
    1: DEFAULT_FILTER_KEYWORDS_V1,
    2: DEFAULT_FILTER_KEYWORDS_V2,
}
DEFAULT_FILTER_VERSION = max(DEFAULT_FILTER_SETS)
DEFAULT_FILTER_KEYWORDS = DEFAULT_FILTER_KEYWORDS_V1 + DEFAULT_FILTER_KEYWORDS_V2


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
    return default_filter_values_since(0)


def default_filter_values_since(version: int) -> list[tuple[str, str]]:
    keywords = [
        keyword
        for filter_version, values in DEFAULT_FILTER_SETS.items()
        if filter_version > version
        for keyword in values
    ]
    return parse_filter_values("\n".join(keywords))


def format_filter_list(keywords: list[str], *, max_characters: int = 3000) -> str:
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
                    text="➕ إضافة فلاتر",
                    callback_data="filters:add:start",
                ),
                InlineKeyboardButton(
                    text="🗑 حذف فلاتر",
                    callback_data="filters:remove:start",
                ),
            ]
        ]
    )


def filters_confirmation_keyboard(action: str = "add") -> InlineKeyboardMarkup:
    if action not in {"add", "remove"}:
        raise ValueError("Unsupported filter action")
    confirm_text = "✅ إضافة" if action == "add" else "🗑 حذف"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=confirm_text,
                    callback_data=f"filters:{action}:confirm",
                ),
                InlineKeyboardButton(
                    text="❌ إلغاء",
                    callback_data=f"filters:{action}:cancel",
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


def format_lead_notification(
    message: CollectedMessage,
    *,
    observer_names: list[str],
    repeated_group_count: int,
    matched_keywords: tuple[str, ...],
    latency_ms: int,
) -> str:
    request_text = message.text.strip() or "[رسالة بدون نص]"
    if len(request_text) > 2400:
        request_text = f"{request_text[:2397]}..."
    username = f"@{message.sender_username}" if message.sender_username else "غير متوفر"
    sender_id = str(message.sender_telegram_id) if message.sender_telegram_id else "غير متوفر"
    observed_at = message.collected_at.astimezone(ZoneInfo("Africa/Cairo"))
    observed_time = observed_at.strftime("%I:%M %p").replace("AM", "ص").replace("PM", "م")
    observers = "، ".join(observer_names) if observer_names else "غير معروف"
    reason = "، ".join(matched_keywords) if matched_keywords else "سياق طلب"
    repetition = (
        f"\n🔁 كرر الطالب نفس الطلب في {repeated_group_count} مجموعات"
        if repeated_group_count > 1
        else ""
    )

    return (
        "🔔 طلب جديد\n"
        f"👤 المرسل: {message.sender_name or 'غير معروف'}\n"
        f"🆔 User ID: {sender_id}\n"
        f"📱 Username: {username}\n"
        f"📦 المجموعة: {message.group.title}\n"
        "✉️ الطلب:\n"
        f"{request_text}\n"
        f"🕐 وقت الرصد: {observed_time}\n"
        f"🤖 الحساب الراصد: {observers}\n"
        f"🎯 سبب الالتقاط: {reason}"
        f"{repetition}\n"
        f"⚡ زمن الوصول: {latency_ms} ms\n"
        "━━━━━━━━━━━━━━\n"
        "💾 تم حفظ بيانات المرسل"
    )


def lead_notification_keyboard(
    message: CollectedMessage,
) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    if message.original_message_link:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📩 فتح الرسالة",
                    url=message.original_message_link,
                )
            ]
        )
    if message.sender_username:
        rows.append(
            [
                InlineKeyboardButton(
                    text="👤 فتح حساب الطالب",
                    url=f"https://t.me/{message.sender_username}",
                )
            ]
        )
    elif message.sender_telegram_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🆔 بيانات الطالب",
                    callback_data=f"student:{message.sender_telegram_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
