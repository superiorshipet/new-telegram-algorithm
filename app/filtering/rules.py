import hashlib
import re
from dataclasses import dataclass

STRONG_REQUEST_PHRASES = (
    "احتاج",
    "محتاج",
    "ابي",
    "ابغى",
    "من يعرف",
    "مين يسوي",
    "من يقدر",
    "احتاج احد",
    "ابحث عن",
    "مطلوب",
    "احد يسوي",
    "حد يسوي",
    "حد فاهم",
    "حد يفهم",
    "يساعدني",
)

REQUEST_VERBS = (
    "يسوي",
    "تسوي",
    "يسويه",
    "يسويلي",
    "يشرح",
    "تشرح",
    "يبرمج",
    "يصمم",
    "يرسم",
    "يحل",
    "تحل",
    "يعدل",
    "تعدل",
    "يلخص",
    "تلخص",
    "يساعد",
    "تساعد",
    "يحله",
    "تعرفون",
)

REQUEST_MARKERS = (
    "مين",
    "من",
    "احد",
    "حد",
    "ممكن",
    "لو سمحت",
    "لو سمحتم",
)


@dataclass(frozen=True, slots=True)
class LeadMatch:
    is_lead: bool
    score: int
    matched_keywords: tuple[str, ...]
    matched_intents: tuple[str, ...]

    @property
    def reason(self) -> str:
        parts: list[str] = []
        if self.matched_keywords:
            parts.append("كلمات: " + "، ".join(self.matched_keywords))
        if self.matched_intents:
            parts.append("صيغة طلب: " + "، ".join(self.matched_intents))
        return " | ".join(parts)


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def _starts_with_phrase(text: str, phrase: str) -> bool:
    stripped = text.lstrip(" \t\n.,،:؛!?؟-_ـ")
    return re.match(rf"{re.escape(phrase)}(?!\w)", stripped) is not None


def classify_lead(normalized_text: str, keywords: list[str]) -> LeadMatch:
    matched_keywords = tuple(
        keyword for keyword in keywords if _contains_phrase(normalized_text, keyword)
    )
    strong_intents = tuple(
        phrase for phrase in STRONG_REQUEST_PHRASES if _contains_phrase(normalized_text, phrase)
    )
    verb_intents = tuple(verb for verb in REQUEST_VERBS if _contains_phrase(normalized_text, verb))
    matched_intents = tuple(dict.fromkeys((*strong_intents, *verb_intents)))
    context_keywords = tuple(
        keyword for keyword in matched_keywords if keyword not in matched_intents
    )
    word_count = len(normalized_text.split())
    has_explicit_request_context = bool(strong_intents) and (
        bool(context_keywords) or word_count >= 3
    )
    has_verb_request_context = bool(verb_intents and context_keywords) and (
        any(_starts_with_phrase(normalized_text, verb) for verb in verb_intents)
        or any(_contains_phrase(normalized_text, marker) for marker in REQUEST_MARKERS)
        or "?" in normalized_text
        or "؟" in normalized_text
    )
    has_request_context = has_explicit_request_context or has_verb_request_context

    score = min(len(matched_keywords), 3) * 2
    if strong_intents:
        score += 3
    elif verb_intents:
        score += 2

    return LeadMatch(
        is_lead=bool(matched_keywords and matched_intents and has_request_context and score >= 4),
        score=score,
        matched_keywords=matched_keywords,
        matched_intents=matched_intents,
    )


def build_content_hash(
    telegram_chat_id: int,
    telegram_message_id: int,
    normalized_text: str,
) -> str:
    canonical = f"{telegram_chat_id}:{telegram_message_id}:{normalized_text}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_text_fingerprint(normalized_text: str) -> str:
    without_punctuation = re.sub(r"[^\w\s]", " ", normalized_text)
    canonical = " ".join(without_punctuation.split())
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def message_identity(telegram_chat_id: int, telegram_message_id: int) -> tuple[int, int]:
    """Canonical Telegram identity used by the database uniqueness constraint."""
    return telegram_chat_id, telegram_message_id
