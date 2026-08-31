from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

from telethon.events import NewMessage

from app.collector.queue import MessageQueue
from app.database.repositories.messages import NewCollectedMessage
from app.filtering import (
    build_content_hash,
    build_text_fingerprint,
    normalize_arabic,
)

logger = logging.getLogger(__name__)


def build_message_link(
    telegram_chat_id: int,
    telegram_message_id: int,
    username: str | None,
) -> str | None:
    if username:
        return f"https://t.me/{username}/{telegram_message_id}"
    chat_id_text = str(abs(telegram_chat_id))
    if chat_id_text.startswith("100"):
        return f"https://t.me/c/{chat_id_text[3:]}/{telegram_message_id}"
    return None


def create_new_message_handler(
    source_account_id: uuid.UUID,
    queue: MessageQueue,
) -> Callable[[NewMessage.Event], Awaitable[None]]:
    async def handle(event: NewMessage.Event) -> None:
        if not event.is_group or event.chat_id is None:
            return

        try:
            chat = await event.get_chat()
            sender = await event.get_sender()
            text = event.raw_text or ""
            normalized_text = normalize_arabic(text)
            chat_id = int(event.chat_id)
            message_id = int(event.message.id)
            username = getattr(chat, "username", None)
            sender_first_name = getattr(sender, "first_name", None)
            sender_last_name = getattr(sender, "last_name", None)
            sender_name = (
                " ".join(part for part in (sender_first_name, sender_last_name) if part) or None
            )

            await queue.put(
                NewCollectedMessage(
                    telegram_chat_id=chat_id,
                    group_title=getattr(chat, "title", None) or str(chat_id),
                    group_username=username,
                    telegram_message_id=message_id,
                    sender_telegram_id=getattr(sender, "id", None),
                    sender_name=sender_name,
                    sender_username=getattr(sender, "username", None),
                    text=text,
                    normalized_text=normalized_text,
                    original_message_link=build_message_link(chat_id, message_id, username),
                    message_date=event.message.date,
                    source_account_id=source_account_id,
                    content_hash=build_content_hash(chat_id, message_id, normalized_text),
                    text_fingerprint=build_text_fingerprint(normalized_text),
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - Telegram event boundary
            logger.error(
                "telegram_message_handler_failed",
                extra={
                    "telegram_chat_id": event.chat_id,
                    "telegram_message_id": getattr(event.message, "id", None),
                    "source_account_id": str(source_account_id),
                    "error_code": type(exc).__name__,
                },
            )

    return handle
