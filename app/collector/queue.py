from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.repositories.messages import MessageRepository, NewCollectedMessage

logger = logging.getLogger(__name__)


class MessageQueue:
    def __init__(
        self,
        max_size: int,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._queue: asyncio.Queue[NewCollectedMessage] = asyncio.Queue(maxsize=max_size)
        self._session_factory = session_factory

    async def put(self, item: NewCollectedMessage) -> None:
        await self._queue.put(item)

    async def run_writer(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                await self._persist_with_retry(item)
            finally:
                self._queue.task_done()

    async def _persist_with_retry(self, item: NewCollectedMessage) -> None:
        attempt = 0
        while True:
            attempt += 1
            try:
                async with self._session_factory() as session:
                    result = await MessageRepository(session).save_if_new(item)
                    await session.commit()
                logger.info(
                    "message_persisted",
                    extra={
                        "telegram_chat_id": item.telegram_chat_id,
                        "telegram_message_id": item.telegram_message_id,
                        "message_inserted": result.message_inserted,
                        "observation_inserted": result.observation_inserted,
                        "persistence_latency_ms": max(
                            0,
                            int(
                                (datetime.now(UTC) - item.message_date).total_seconds()
                                * 1000
                            ),
                        ),
                        "queue_depth": self._queue.qsize(),
                    },
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - durable writer retry boundary
                logger.error(
                    "message_persist_failed error_code=%s attempt=%d",
                    type(exc).__name__,
                    attempt,
                    extra={
                        "telegram_chat_id": item.telegram_chat_id,
                        "telegram_message_id": item.telegram_message_id,
                        "attempt": attempt,
                    },
                )
                await asyncio.sleep(min(2 ** min(attempt - 1, 4), 15))

    async def join(self) -> None:
        await self._queue.join()
