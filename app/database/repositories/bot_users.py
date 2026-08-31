import uuid

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BotUser


class BotUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        username: str | None,
        first_name: str | None,
    ) -> BotUser:
        statement = insert(BotUser).values(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            username=username,
            first_name=first_name,
            is_active=True,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[BotUser.telegram_user_id],
            set_={
                "telegram_chat_id": statement.excluded.telegram_chat_id,
                "username": statement.excluded.username,
                "first_name": statement.excluded.first_name,
                "is_active": True,
                "updated_at": func.now(),
            },
        )
        return (await self._session.execute(statement.returning(BotUser))).scalar_one()

    async def get_by_telegram_id(self, telegram_user_id: int) -> BotUser | None:
        return await self._session.scalar(
            select(BotUser).where(BotUser.telegram_user_id == telegram_user_id)
        )

    async def set_notifications_active(self, telegram_user_id: int, *, active: bool) -> bool:
        result = await self._session.execute(
            update(BotUser)
            .where(BotUser.telegram_user_id == telegram_user_id)
            .values(is_active=active, updated_at=func.now())
            .returning(BotUser.id)
        )
        return result.scalar_one_or_none() is not None

    async def mark_default_filters_seeded(self, bot_user_id: uuid.UUID, version: int) -> None:
        await self._session.execute(
            update(BotUser)
            .where(BotUser.id == bot_user_id)
            .values(
                default_filters_seeded=True,
                default_filter_version=version,
                updated_at=func.now(),
            )
        )
