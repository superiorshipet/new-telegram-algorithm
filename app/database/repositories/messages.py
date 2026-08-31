import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import CollectedMessage, TelegramGroup


@dataclass(frozen=True, slots=True)
class NewCollectedMessage:
    telegram_chat_id: int
    group_title: str
    group_username: str | None
    telegram_message_id: int
    sender_telegram_id: int | None
    sender_name: str | None
    sender_username: str | None
    text: str
    normalized_text: str
    original_message_link: str | None
    message_date: datetime
    source_account_id: uuid.UUID
    content_hash: str


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_if_new(self, item: NewCollectedMessage) -> bool:
        group_insert = insert(TelegramGroup).values(
            telegram_chat_id=item.telegram_chat_id,
            title=item.group_title,
            username=item.group_username,
            is_active=True,
        )
        group_insert = group_insert.on_conflict_do_update(
            index_elements=[TelegramGroup.telegram_chat_id],
            set_={
                "title": group_insert.excluded.title,
                "username": group_insert.excluded.username,
                "updated_at": func.now(),
            },
        ).returning(TelegramGroup.id)
        group_id = (await self._session.execute(group_insert)).scalar_one()

        message_insert = (
            insert(CollectedMessage)
            .values(
                telegram_group_id=group_id,
                telegram_message_id=item.telegram_message_id,
                sender_telegram_id=item.sender_telegram_id,
                sender_name=item.sender_name,
                sender_username=item.sender_username,
                text=item.text,
                normalized_text=item.normalized_text,
                original_message_link=item.original_message_link,
                message_date=item.message_date,
                source_account_id=item.source_account_id,
                content_hash=item.content_hash,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    CollectedMessage.telegram_group_id,
                    CollectedMessage.telegram_message_id,
                ]
            )
            .returning(CollectedMessage.id)
        )
        return (await self._session.execute(message_insert)).scalar_one_or_none() is not None
