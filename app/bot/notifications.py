from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

import asyncpg
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.services import format_lead_notification, lead_notification_keyboard
from app.database.repositories import BotFeatureRepository, NotificationRepository
from app.filtering import classify_lead

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    # Purge processed rows after this many notifications OR this many seconds,
    # whichever threshold is hit first.
    _PURGE_EVERY_N = 1000
    _PURGE_EVERY_SECONDS = 6 * 60 * 60  # 6 hours

    def __init__(
        self,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
        database_url: str,
        *,
        concurrency: int = 8,
    ) -> None:
        self._bot = bot
        self._session_factory = session_factory
        self._database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self._concurrency = concurrency
        self._wake = asyncio.Event()
        self._processed_since_purge: int = 0
        self._last_purge_at: float = 0.0  # monotonic seconds

    async def run(self, stop_event: asyncio.Event) -> None:
        listener: asyncpg.Connection | None = None
        self._last_purge_at = time.monotonic()
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
                self._wake.clear()
                while processed := await self._process_ready_batch():
                    self._processed_since_purge += processed
                    if self._processed_since_purge >= self._PURGE_EVERY_N:
                        await self._maybe_purge()
                    if stop_event.is_set():
                        break
                # Also purge on the idle path (time-based trigger)
                await self._maybe_purge()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=1)
                except TimeoutError:
                    pass
        finally:
            if listener is not None:
                await listener.close()

    async def _maybe_purge(self) -> None:
        """Purge processed outbox rows when the count or time threshold is met."""
        elapsed = time.monotonic() - self._last_purge_at
        if (
            self._processed_since_purge < self._PURGE_EVERY_N
            and elapsed < self._PURGE_EVERY_SECONDS
        ):
            return
        try:
            async with self._session_factory() as session, session.begin():
                outbox_del, msg_del = await NotificationRepository(session).purge_processed_rows()
            logger.info(
                "outbox_purge_complete",
                extra={"outbox_deleted": outbox_del, "messages_deleted": msg_del},
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - purge is best-effort
            logger.error(
                "outbox_purge_failed",
                extra={"error_code": type(exc).__name__},
            )
        finally:
            self._processed_since_purge = 0
            self._last_purge_at = time.monotonic()

    def _notification_received(
        self,
        connection: asyncpg.Connection,
        process_id: int,
        channel: str,
        payload: str,
    ) -> None:
        del connection, process_id, channel, payload
        self._wake.set()

    async def _process_ready_batch(self) -> int:
        # Probe once so the one-second recovery poll costs one query while idle.
        # Only fan out when work exists, keeping backlog throughput high without
        # creating constant database load during quiet periods.
        if not await self._process_next():
            return 0
        if self._concurrency == 1:
            return 1
        results = await asyncio.gather(
            *(self._process_next() for _ in range(self._concurrency - 1))
        )
        return 1 + sum(results)

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
                recipient = await repository.load_recipient(outbox.bot_user_id)
                if message is None or recipient is None or not recipient.is_active:
                    await repository.mark_skipped(outbox.id)
                    return True

                filters = await BotFeatureRepository(session).list_keywords(recipient.id)
                match = classify_lead(
                    message.normalized_text,
                    [item.normalized_keyword for item in filters],
                )
                await repository.save_classification(
                    outbox.id,
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
                collector_latency_ms = max(
                    0,
                    int((message.collected_at - message.message_date).total_seconds() * 1000),
                )
                notification_text = format_lead_notification(
                    message,
                    observer_names=observer_names,
                    repeated_group_count=repeated_group_count,
                    matched_keywords=match.matched_keywords,
                    latency_ms=latency_ms,
                )
                try:
                    await self._bot.send_message(
                        chat_id=recipient.telegram_chat_id,
                        text=notification_text,
                        reply_markup=lead_notification_keyboard(message),
                    )
                except TelegramBadRequest:
                    logger.warning(
                        "notification_keyboard_rejected",
                        extra={"outbox_id": str(outbox.id)},
                    )
                    await self._bot.send_message(
                        chat_id=recipient.telegram_chat_id,
                        text=notification_text,
                    )
                await repository.mark_sent(outbox.id, latency_ms)

            logger.info(
                "lead_notification_sent",
                extra={
                    "outbox_id": str(outbox_id),
                    "latency_ms": latency_ms,
                    "collector_latency_ms": collector_latency_ms,
                    "dispatch_latency_ms": max(0, latency_ms - collector_latency_ms),
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
