from __future__ import annotations

import asyncio
from datetime import UTC

from app.common.config import get_settings
from app.database.models import SourceAccount
from app.database.repositories import SourceAccountRepository
from app.database.session import Database


def format_account_status(accounts: list[SourceAccount]) -> str:
    active_count = sum(account.is_active for account in accounts)
    connected_count = sum(
        account.is_active and account.status == "connected" for account in accounts
    )
    lines = [
        (
            f"collector_accounts total={len(accounts)} active={active_count} "
            f"connected={connected_count}"
        )
    ]
    for account in accounts:
        last_connected = (
            account.last_connected_at.astimezone(UTC).isoformat(timespec="seconds")
            if account.last_connected_at
            else "never"
        )
        lines.append(
            f"- {account.name}: status={account.status} active={str(account.is_active).lower()} "
            f"last_connected_at={last_connected}"
        )
    return "\n".join(lines)


async def run() -> None:
    database = Database(get_settings())
    try:
        async with database.session_factory() as session:
            accounts = await SourceAccountRepository(session).list_all()
        print(format_account_status(accounts))
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(run())
