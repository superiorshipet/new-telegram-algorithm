import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, literal, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    BotUser,
    CollectedMessage,
    MessageObservation,
    NotificationOutbox,
    TelegramGroup,
)


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
    text_fingerprint: str


@dataclass(frozen=True, slots=True)
class PersistedMessage:
    message_id: uuid.UUID
    message_inserted: bool
    observation_inserted: bool


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_if_new(self, item: NewCollectedMessage) -> PersistedMessage:
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
                text_fingerprint=item.text_fingerprint,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    CollectedMessage.telegram_group_id,
                    CollectedMessage.telegram_message_id,
                ]
            )
            .returning(CollectedMessage.id)
        )
        message_id = (await self._session.execute(message_insert)).scalar_one_or_none()
        message_inserted = message_id is not None
        if message_id is None:
            message_id = await self._session.scalar(
                select(CollectedMessage.id)
                .where(CollectedMessage.telegram_group_id == group_id)
                .where(CollectedMessage.telegram_message_id == item.telegram_message_id)
            )
            if message_id is None:
                raise RuntimeError("Deduplicated Telegram message could not be resolved")

        observation_insert = (
            insert(MessageObservation)
            .values(
                collected_message_id=message_id,
                source_account_id=item.source_account_id,
            )
            .on_conflict_do_nothing(constraint="uq_message_observations_message_source")
            .returning(MessageObservation.id)
        )
        observation_inserted = (
            await self._session.execute(observation_insert)
        ).scalar_one_or_none() is not None

        if message_inserted:
            await self._session.execute(_notification_outbox_insert(message_id))

        return PersistedMessage(
            message_id=message_id,
            message_inserted=message_inserted,
            observation_inserted=observation_inserted,
        )


def _notification_outbox_insert(message_id: uuid.UUID):
    recipients = select(
        func.gen_random_uuid(),
        literal(message_id),
        BotUser.id,
        func.now() + text("interval '1 second'"),
    ).where(BotUser.is_active.is_(True))
    return insert(NotificationOutbox).from_select(
        ["id", "collected_message_id", "bot_user_id", "available_at"],
        recipients,
        include_defaults=False,
    )
