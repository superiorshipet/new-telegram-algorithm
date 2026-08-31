from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

import asyncpg
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.services import format_lead_notification, lead_notification_keyboard
from app.database.repositories import (
    BotFeatureRepository,
    BotUserRepository,
    NotificationRepository,
)
from app.filtering import classify_lead

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    def __init__(
        self,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
        database_url: str,
        owner_telegram_id: int,
    ) -> None:
        self._bot = bot
        self._session_factory = session_factory
        self._database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self._owner_telegram_id = owner_telegram_id
        self._wake = asyncio.Event()

    async def run(self, stop_event: asyncio.Event) -> None:
        listener: asyncpg.Connection | None = None
        try:
            try:
                listener = await asyncpg.connect(self._database_url, timeout=10)
                await listener.add_listener("lead_notifications", self._notification_received)
                logger.info("notification_listener_connected")
            except Exception as exc:  # noqa: BLE001 - listener has polling fallback
                logger.error(
                    "notification_listener_unavailable",
                    extra={"error_code": type(exc).__name__},
                )

            self._wake.set()
            while not stop_event.is_set():
                while await self._process_next():
                    if stop_event.is_set():
                        break
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=1)
                except TimeoutError:
                    pass
        finally:
            if listener is not None:
                await listener.close()

    def _notification_received(
        self,
        connection: asyncpg.Connection,
        process_id: int,
        channel: str,
        payload: str,
    ) -> None:
        del connection, process_id, channel, payload
        self._wake.set()

    async def _process_next(self) -> bool:
        outbox_id: uuid.UUID | None = None
        try:
            async with self._session_factory() as session, session.begin():
                repository = NotificationRepository(session)
                outbox = await repository.claim_next()
                if outbox is None:
                    return False
                outbox_id = outbox.id
                message = await repository.load_message(outbox.collected_message_id)
                owner = await BotUserRepository(session).get_by_telegram_id(self._owner_telegram_id)
                if message is None or owner is None or not owner.is_active:
                    await repository.mark_skipped(outbox.id)
                    return True

                filters = await BotFeatureRepository(session).list_keywords(owner.id)
                match = classify_lead(
                    message.normalized_text,
                    [item.normalized_keyword for item in filters],
                )
                await repository.save_classification(
                    message.id,
                    is_lead=match.is_lead,
                    score=match.score,
                    matched_keywords=list(match.matched_keywords),
                    reason=match.reason,
                )
                if not match.is_lead:
                    await repository.mark_skipped(outbox.id)
                    return True

                observer_names = await repository.observer_names(message.id)
                repeated_group_count = await repository.repeated_group_count(message)
                latency_ms = max(
                    0,
                    int((datetime.now(UTC) - message.message_date).total_seconds() * 1000),
                )
                await self._bot.send_message(
                    chat_id=owner.telegram_chat_id,
                    text=format_lead_notification(
                        message,
                        observer_names=observer_names,
                        repeated_group_count=repeated_group_count,
                        matched_keywords=match.matched_keywords,
                        latency_ms=latency_ms,
                    ),
                    reply_markup=lead_notification_keyboard(message),
                )
                await repository.mark_sent(outbox.id, latency_ms)

            logger.info(
                "lead_notification_sent",
                extra={
                    "outbox_id": str(outbox_id),
                    "latency_ms": latency_ms,
                },
            )
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - durable worker retry boundary
            if outbox_id is not None:
                try:
                    async with self._session_factory() as session:
                        await NotificationRepository(session).record_failure(
                            outbox_id, type(exc).__name__
                        )
                        await session.commit()
                except Exception as record_exc:  # noqa: BLE001 - do not crash worker
                    logger.error(
                        "notification_failure_record_failed",
                        extra={"error_code": type(record_exc).__name__},
                    )
            logger.error(
                "lead_notification_failed",
                extra={
                    "outbox_id": str(outbox_id) if outbox_id else None,
                    "error_code": type(exc).__name__,
                },
            )
            return False
