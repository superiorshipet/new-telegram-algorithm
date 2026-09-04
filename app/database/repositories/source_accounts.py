import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SourceAccount

MAX_ACTIVE_SOURCE_ACCOUNTS = 3


@dataclass(frozen=True, slots=True)
class SaveSourceAccountResult:
    account: SourceAccount | None
    limit_reached: bool = False


class SourceAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_enabled(self) -> list[SourceAccount]:
        now = datetime.now(UTC)
        result = await self._session.scalars(
            select(SourceAccount)
            .where(SourceAccount.is_active.is_(True))
            .where(SourceAccount.status != "unauthorized")
            .where(
                (SourceAccount.flood_wait_until.is_(None)) | (SourceAccount.flood_wait_until <= now)
            )
            .order_by(SourceAccount.created_at)
        )
        return list(result)

    async def count_active(self) -> int:
        count = await self._session.scalar(
            select(func.count(SourceAccount.id)).where(SourceAccount.is_active.is_(True))
        )
        return count or 0

    async def list_all(self) -> list[SourceAccount]:
        result = await self._session.scalars(
            select(SourceAccount).order_by(SourceAccount.created_at, SourceAccount.name)
        )
        return list(result)

    async def save_authenticated(
        self,
        *,
        name: str,
        phone_number_masked: str | None,
        session_string_encrypted: str,
        api_id_encrypted: str,
        api_hash_encrypted: str,
    ) -> SaveSourceAccountResult:
        # Serialize account activation so concurrent bot actions cannot exceed the limit.
        await self._session.execute(select(func.pg_advisory_xact_lock(742_031)))
        existing = await self._session.scalar(
            select(SourceAccount).where(SourceAccount.name == name).with_for_update()
        )
        active_count = await self._session.scalar(
            select(func.count(SourceAccount.id)).where(SourceAccount.is_active.is_(True))
        )
        if (existing is None or not existing.is_active) and (active_count or 0) >= (
            MAX_ACTIVE_SOURCE_ACCOUNTS
        ):
            return SaveSourceAccountResult(account=None, limit_reached=True)

        statement = insert(SourceAccount).values(
            name=name,
            phone_number_masked=phone_number_masked,
            session_string_encrypted=session_string_encrypted,
            api_id_encrypted=api_id_encrypted,
            api_hash_encrypted=api_hash_encrypted,
            is_active=True,
            status="pending",
            flood_wait_until=None,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[SourceAccount.name],
            set_={
                "phone_number_masked": statement.excluded.phone_number_masked,
                "session_string_encrypted": statement.excluded.session_string_encrypted,
                "api_id_encrypted": statement.excluded.api_id_encrypted,
                "api_hash_encrypted": statement.excluded.api_hash_encrypted,
                "is_active": True,
                "status": "pending",
                "flood_wait_until": None,
                "updated_at": func.now(),
            },
        ).returning(SourceAccount)
        account = (await self._session.execute(statement)).scalar_one()
        return SaveSourceAccountResult(account=account)

    async def set_active(self, account_id: uuid.UUID, *, active: bool) -> str:
        await self._session.execute(select(func.pg_advisory_xact_lock(742_031)))
        account = await self._session.get(SourceAccount, account_id, with_for_update=True)
        if account is None:
            return "not_found"
        if active and not account.is_active:
            active_count = await self._session.scalar(
                select(func.count(SourceAccount.id)).where(SourceAccount.is_active.is_(True))
            )
            if (active_count or 0) >= MAX_ACTIVE_SOURCE_ACCOUNTS:
                return "limit_reached"
        account.is_active = active
        account.status = "pending" if active else "disabled"
        account.flood_wait_until = None
        account.updated_at = func.now()
        return "updated"

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
