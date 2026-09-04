import asyncio
from unittest.mock import AsyncMock

from app.collector.client_manager import CollectorClientManager


async def test_reconciler_applies_database_account_changes() -> None:
    stop_event = asyncio.Event()
    manager = CollectorClientManager(AsyncMock(), AsyncMock(), AsyncMock())
    manager.reconcile_enabled = AsyncMock(side_effect=stop_event.set)  # type: ignore[method-assign]

    await manager.run_reconciler(stop_event, interval_seconds=0.001)

    manager.reconcile_enabled.assert_awaited_once()
