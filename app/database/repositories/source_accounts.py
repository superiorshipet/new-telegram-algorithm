import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SourceAccount


class SourceAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_enabled(self) -> list[SourceAccount]:
        now = datetime.now(UTC)
        result = await self._session.scalars(
            select(SourceAccount)
            .where(SourceAccount.is_active.is_(True))
            .where(
                (SourceAccount.flood_wait_until.is_(None)) | (SourceAccount.flood_wait_until <= now)
            )
            .order_by(SourceAccount.created_at)
        )
        return list(result)

    async def list_all(self) -> list[SourceAccount]:
        result = await self._session.scalars(
            select(SourceAccount).order_by(SourceAccount.created_at, SourceAccount.name)
        )
        return list(result)

    async def set_status(
        self,
        account_id: uuid.UUID,
        status: str,
        *,
        connected: bool = False,
        flood_wait_until: datetime | None = None,
    ) -> None:
        values: dict[str, object] = {
            "status": status,
            "flood_wait_until": flood_wait_until,
            "updated_at": func.now(),
        }
        if connected:
            values["last_connected_at"] = datetime.now(UTC)
        await self._session.execute(
            update(SourceAccount).where(SourceAccount.id == account_id).values(**values)
        )
