from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telethon import TelegramClient, events
from telethon.errors import AuthKeyError, FloodWaitError
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
        self._clients: dict[uuid.UUID, TelegramClient] = {}
        self._reconcile_lock = asyncio.Lock()

    async def start_enabled(self) -> int:
        async with self._session_factory() as session:
            accounts = await SourceAccountRepository(session).list_enabled()

        for account in accounts:
            await self._start_account(account)
        return len(self._clients)

    async def run_reconciler(
        self,
        stop_event: asyncio.Event,
        *,
        interval_seconds: float = 5,
    ) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except TimeoutError:
                await self.reconcile_enabled()

    async def reconcile_enabled(self) -> None:
        async with self._reconcile_lock:
            async with self._session_factory() as session:
                enabled_accounts = await SourceAccountRepository(session).list_enabled()
            enabled_by_id = {account.id: account for account in enabled_accounts}

            for account_id, client in list(self._clients.items()):
                if account_id in enabled_by_id and client.is_connected():
                    continue
                await self._disconnect_client(client)
                self._clients.pop(account_id, None)

            for account_id, account in enabled_by_id.items():
                if account_id not in self._clients:
                    await self._start_account(account)

    async def _start_account(self, account: SourceAccount) -> None:
        client: TelegramClient | None = None
        try:
            api_id = int(self._cipher.decrypt(account.api_id_encrypted))
            api_hash = self._cipher.decrypt(account.api_hash_encrypted)
            string_session = self._cipher.decrypt(account.session_string_encrypted)
            client = TelegramClient(StringSession(string_session), api_id, api_hash)
            client.add_event_handler(
                create_new_message_handler(account.id, self._queue),
                events.NewMessage(),
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

            await self._set_status(account, "connected", connected=True)
            self._clients[account.id] = client
            logger.info(
                "source_account_connected",
                extra={"source_account_id": str(account.id)},
            )
        except AuthKeyError as exc:
            await self._disconnect_failed_client(client)
            await self._set_status(account, "unauthorized")
            logger.error(
                "source_account_session_invalid error_code=%s",
                type(exc).__name__,
                extra={"source_account_id": str(account.id)},
            )
        except FloodWaitError as exc:
            await self._disconnect_failed_client(client)
            until = datetime.now(UTC) + timedelta(seconds=exc.seconds)
            await self._set_status(account, "flood_wait", flood_wait_until=until)
            logger.warning(
                "source_account_flood_wait",
                extra={
                    "source_account_id": str(account.id),
                    "wait_seconds": exc.seconds,
                },
            )
        except Exception as exc:  # noqa: BLE001 - account isolation boundary
            await self._disconnect_failed_client(client)
            await self._set_status(
                account,
                "error",
                flood_wait_until=datetime.now(UTC) + timedelta(minutes=1),
            )
            logger.error(
                "source_account_connection_failed error_code=%s",
                type(exc).__name__,
                extra={
                    "source_account_id": str(account.id),
                },
            )

    @staticmethod
    async def _disconnect_failed_client(client: TelegramClient | None) -> None:
        if client is None:
            return
        try:
            await client.disconnect()
        except Exception as exc:  # noqa: BLE001 - preserve original connection failure
            logger.error(
                "failed_client_cleanup error_code=%s",
                type(exc).__name__,
            )

    @staticmethod
    async def _disconnect_client(client: TelegramClient) -> None:
        try:
            await client.disconnect()
        except Exception as exc:  # noqa: BLE001 - account isolation boundary
            logger.error(
                "source_account_disconnect_failed",
                extra={"error_code": type(exc).__name__},
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
        for client in self._clients.values():
            await self._disconnect_client(client)
        self._clients.clear()
