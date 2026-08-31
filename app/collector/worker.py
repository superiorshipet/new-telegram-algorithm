from __future__ import annotations

import asyncio
import logging
import signal

from app.collector.client_manager import CollectorClientManager
from app.collector.queue import MessageQueue
from app.common.config import get_settings
from app.common.crypto import SecretCipher
from app.common.logging import configure_logging
from app.database.session import Database

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    database = Database(settings)
    queue = MessageQueue(settings.collector_queue_size, database.session_factory)
    manager = CollectorClientManager(
        database.session_factory,
        SecretCipher(settings.require_encryption_key()),
        queue,
    )
    writer_task = asyncio.create_task(queue.run_writer(), name="database-writer")
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_name, stop_event.set)

    try:
        started = await manager.start_enabled()
        logger.info("collector_started", extra={"connected_accounts": started})
        await stop_event.wait()
    finally:
        logger.info("collector_stopping")
        await manager.disconnect_all()
        await queue.join()
        writer_task.cancel()
        await asyncio.gather(writer_task, return_exceptions=True)
        await database.dispose()
        logger.info("collector_stopped")
