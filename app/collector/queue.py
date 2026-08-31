from __future__ import annotations

import asyncio
import logging

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
        for attempt in range(1, 6):
            try:
                async with self._session_factory() as session:
                    inserted = await MessageRepository(session).save_if_new(item)
                    await session.commit()
                logger.info(
                    "message_persisted",
                    extra={
                        "telegram_chat_id": item.telegram_chat_id,
                        "telegram_message_id": item.telegram_message_id,
                        "inserted": inserted,
                    },
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "message_persist_failed",
                    extra={
                        "telegram_chat_id": item.telegram_chat_id,
                        "telegram_message_id": item.telegram_message_id,
                        "attempt": attempt,
                    },
                )
                if attempt == 5:
                    logger.error(
                        "message_discarded_after_retries",
                        extra={
                            "telegram_chat_id": item.telegram_chat_id,
                            "telegram_message_id": item.telegram_message_id,
                        },
                    )
                    return
                await asyncio.sleep(min(2 ** (attempt - 1), 15))

    async def join(self) -> None:
        await self._queue.join()
