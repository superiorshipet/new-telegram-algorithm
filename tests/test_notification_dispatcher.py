from unittest.mock import AsyncMock

from app.bot.notifications import NotificationDispatcher


async def test_dispatcher_processes_ready_notifications_concurrently() -> None:
    dispatcher = NotificationDispatcher(
        AsyncMock(),
        AsyncMock(),
        "postgresql+asyncpg://user:pass@database/app",
        concurrency=4,
    )
    dispatcher._process_next = AsyncMock(  # type: ignore[method-assign]
        side_effect=[True, True, False, True]
    )

    processed = await dispatcher._process_ready_batch()

    assert processed == 3
    assert dispatcher._process_next.await_count == 4


async def test_idle_dispatcher_uses_only_one_database_probe() -> None:
    dispatcher = NotificationDispatcher(
        AsyncMock(),
        AsyncMock(),
        "postgresql+asyncpg://user:pass@database/app",
        concurrency=8,
    )
    dispatcher._process_next = AsyncMock(return_value=False)  # type: ignore[method-assign]

    processed = await dispatcher._process_ready_batch()

    assert processed == 0
    dispatcher._process_next.assert_awaited_once()
