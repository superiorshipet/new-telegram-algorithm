from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database.models import (
    BotUserKeyword,
    CollectedMessage,
    SavedMessage,
)


@dataclass(frozen=True, slots=True)
class UserFeatureCounts:
    keyword_count: int
    saved_count: int


class BotFeatureRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_keywords(self, bot_user_id: uuid.UUID) -> list[BotUserKeyword]:
        result = await self._session.scalars(
            select(BotUserKeyword)
            .where(BotUserKeyword.bot_user_id == bot_user_id)
            .order_by(BotUserKeyword.created_at, BotUserKeyword.keyword)
        )
        return list(result)

    async def add_keywords(
        self,
        bot_user_id: uuid.UUID,
        keywords: list[tuple[str, str]],
    ) -> int:
        if not keywords:
            return 0
        statement = (
            insert(BotUserKeyword)
            .values(
                [
                    {
                        "bot_user_id": bot_user_id,
                        "keyword": keyword,
                        "normalized_keyword": normalized,
                    }
                    for keyword, normalized in keywords
                ]
            )
            .on_conflict_do_nothing(constraint="uq_bot_user_keywords_user_normalized")
            .returning(BotUserKeyword.id)
        )
        return len(list((await self._session.scalars(statement)).all()))

    async def remove_keyword(self, bot_user_id: uuid.UUID, normalized_keyword: str) -> bool:
        result = await self._session.execute(
            delete(BotUserKeyword)
            .where(BotUserKeyword.bot_user_id == bot_user_id)
            .where(BotUserKeyword.normalized_keyword == normalized_keyword)
            .returning(BotUserKeyword.id)
        )
        return result.scalar_one_or_none() is not None

    async def clear_keywords(self, bot_user_id: uuid.UUID) -> int:
        result = await self._session.scalars(
            delete(BotUserKeyword)
            .where(BotUserKeyword.bot_user_id == bot_user_id)
            .returning(BotUserKeyword.id)
        )
        return len(list(result.all()))

    async def latest_matching_messages(
        self,
        normalized_keywords: list[str],
        *,
        limit: int = 5,
    ) -> list[CollectedMessage]:
        statement = (
            select(CollectedMessage)
            .options(joinedload(CollectedMessage.group))
            .order_by(CollectedMessage.message_date.desc())
            .limit(limit)
        )
        if normalized_keywords:
            statement = statement.where(
                or_(
                    *(
                        CollectedMessage.normalized_text.contains(keyword, autoescape=True)
                        for keyword in normalized_keywords
                    )
                )
            )
        return list(await self._session.scalars(statement))

    async def save_message(self, bot_user_id: uuid.UUID, message_id: uuid.UUID) -> str:
        exists = await self._session.scalar(
            select(CollectedMessage.id).where(CollectedMessage.id == message_id)
        )
        if exists is None:
            return "not_found"

        statement = (
            insert(SavedMessage)
            .values(bot_user_id=bot_user_id, collected_message_id=message_id)
            .on_conflict_do_nothing(constraint="uq_saved_messages_user_message")
            .returning(SavedMessage.id)
        )
        inserted = (await self._session.execute(statement)).scalar_one_or_none()
        return "saved" if inserted is not None else "already_saved"

    async def remove_saved_message(self, bot_user_id: uuid.UUID, message_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(SavedMessage)
            .where(SavedMessage.bot_user_id == bot_user_id)
            .where(SavedMessage.collected_message_id == message_id)
            .returning(SavedMessage.id)
        )
        return result.scalar_one_or_none() is not None

    async def list_saved_messages(
        self, bot_user_id: uuid.UUID, *, limit: int = 10
    ) -> list[CollectedMessage]:
        result = await self._session.scalars(
            select(CollectedMessage)
            .join(
                SavedMessage,
                SavedMessage.collected_message_id == CollectedMessage.id,
            )
            .where(SavedMessage.bot_user_id == bot_user_id)
            .options(joinedload(CollectedMessage.group))
            .order_by(SavedMessage.created_at.desc())
            .limit(limit)
        )
        return list(result)

    async def get_counts(self, bot_user_id: uuid.UUID) -> UserFeatureCounts:
        keyword_count = await self._session.scalar(
            select(func.count(BotUserKeyword.id)).where(BotUserKeyword.bot_user_id == bot_user_id)
        )
        saved_count = await self._session.scalar(
            select(func.count(SavedMessage.id)).where(SavedMessage.bot_user_id == bot_user_id)
        )
        return UserFeatureCounts(
            keyword_count=keyword_count or 0,
            saved_count=saved_count or 0,
        )
