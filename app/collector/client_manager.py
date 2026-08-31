from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

from app.collector.handlers import create_new_message_handler
from app.collector.queue import MessageQueue
from app.common.crypto import SecretCipher
from app.database.models import SourceAccount
from app.database.repositories import SourceAccountRepository

logger = logging.getLogger(__name__)


class CollectorClientManager:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cipher: SecretCipher,
        queue: MessageQueue,
    ) -> None:
        self._session_factory = session_factory
        self._cipher = cipher
        self._queue = queue
        self._clients: list[TelegramClient] = []

    async def start_enabled(self) -> int:
        async with self._session_factory() as session:
            accounts = await SourceAccountRepository(session).list_enabled()

        for account in accounts:
            await self._start_account(account)
        return len(self._clients)

    async def _start_account(self, account: SourceAccount) -> None:
        try:
            api_id = int(self._cipher.decrypt(account.api_id_encrypted))
            api_hash = self._cipher.decrypt(account.api_hash_encrypted)
            string_session = self._cipher.decrypt(account.session_string_encrypted)
            client = TelegramClient(StringSession(string_session), api_id, api_hash)
            client.add_event_handler(
                create_new_message_handler(account.id, self._queue),
                events.NewMessage(incoming=True),
            )
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                await self._set_status(account, "unauthorized")
                logger.error(
                    "source_account_unauthorized",
                    extra={"source_account_id": str(account.id)},
                )
                return

            self._clients.append(client)
            await self._set_status(account, "connected", connected=True)
            logger.info(
                "source_account_connected",
                extra={"source_account_id": str(account.id)},
            )
        except FloodWaitError as exc:
            until = datetime.now(UTC) + timedelta(seconds=exc.seconds)
            await self._set_status(account, "flood_wait", flood_wait_until=until)
            logger.warning(
                "source_account_flood_wait",
                extra={
                    "source_account_id": str(account.id),
                    "wait_seconds": exc.seconds,
                },
            )
        except Exception:
            await self._set_status(account, "error")
            logger.exception(
                "source_account_connection_failed",
                extra={"source_account_id": str(account.id)},
            )

    async def _set_status(
        self,
        account: SourceAccount,
        status: str,
        *,
        connected: bool = False,
        flood_wait_until: datetime | None = None,
    ) -> None:
        async with self._session_factory() as session:
            await SourceAccountRepository(session).set_status(
                account.id,
                status,
                connected=connected,
                flood_wait_until=flood_wait_until,
            )
            await session.commit()

    async def disconnect_all(self) -> None:
        for client in self._clients:
            try:
                await client.disconnect()
            except Exception:
                logger.exception("source_account_disconnect_failed")
        self._clients.clear()
