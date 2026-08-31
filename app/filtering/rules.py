import hashlib


def build_content_hash(
    telegram_chat_id: int,
    telegram_message_id: int,
    normalized_text: str,
) -> str:
    canonical = f"{telegram_chat_id}:{telegram_message_id}:{normalized_text}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def message_identity(telegram_chat_id: int, telegram_message_id: int) -> tuple[int, int]:
    """Canonical Telegram identity used by the database uniqueness constraint."""
    return telegram_chat_id, telegram_message_id
