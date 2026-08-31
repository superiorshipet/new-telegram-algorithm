from sqlalchemy import func
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
    ) -> None:
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
        await self._session.execute(statement)
