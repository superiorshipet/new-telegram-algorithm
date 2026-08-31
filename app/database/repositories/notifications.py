from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database.models import (
    BotUser,
    CollectedMessage,
    MessageObservation,
    NotificationOutbox,
    SourceAccount,
)


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim_next(self) -> NotificationOutbox | None:
        return await self._session.scalar(
            select(NotificationOutbox)
            .where(NotificationOutbox.status == "pending")
            .where(NotificationOutbox.available_at <= func.now())
            .where(NotificationOutbox.attempts < 10)
            .order_by(NotificationOutbox.available_at, NotificationOutbox.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )

    async def load_message(self, message_id: uuid.UUID) -> CollectedMessage | None:
        return await self._session.scalar(
            select(CollectedMessage)
            .where(CollectedMessage.id == message_id)
            .options(joinedload(CollectedMessage.group))
        )

    async def load_recipient(self, bot_user_id: uuid.UUID) -> BotUser | None:
        return await self._session.get(BotUser, bot_user_id)

    async def observer_names(self, message_id: uuid.UUID) -> list[str]:
        result = await self._session.scalars(
            select(distinct(SourceAccount.name))
            .join(
                MessageObservation,
                MessageObservation.source_account_id == SourceAccount.id,
            )
            .where(MessageObservation.collected_message_id == message_id)
            .order_by(SourceAccount.name)
        )
        return list(result)

    async def repeated_group_count(self, message: CollectedMessage) -> int:
        if message.sender_telegram_id is None or not message.text_fingerprint:
            return 1
        count = await self._session.scalar(
            select(func.count(distinct(CollectedMessage.telegram_group_id)))
            .where(CollectedMessage.sender_telegram_id == message.sender_telegram_id)
            .where(CollectedMessage.text_fingerprint == message.text_fingerprint)
        )
        return count or 1

    async def save_classification(
        self,
        outbox_id: uuid.UUID,
        message_id: uuid.UUID,
        *,
        is_lead: bool,
        score: int,
        matched_keywords: list[str],
        reason: str,
    ) -> None:
        await self._session.execute(
            update(NotificationOutbox)
            .where(NotificationOutbox.id == outbox_id)
            .values(
                is_lead=is_lead,
                matched_keywords=matched_keywords,
                match_reason=reason or None,
            )
        )
        if not is_lead:
            return
        await self._session.execute(
            update(CollectedMessage)
            .where(CollectedMessage.id == message_id)
            .values(
                is_lead=True,
                preliminary_score=func.greatest(CollectedMessage.preliminary_score, score),
                matched_keywords=matched_keywords,
                match_reason=reason or None,
            )
        )

    async def mark_sent(self, outbox_id: uuid.UUID, latency_ms: int) -> None:
        await self._session.execute(
            update(NotificationOutbox)
            .where(NotificationOutbox.id == outbox_id)
            .values(
                status="sent",
                delivered_at=func.now(),
                latency_ms=latency_ms,
                last_error_code=None,
                updated_at=func.now(),
            )
        )

    async def mark_skipped(self, outbox_id: uuid.UUID) -> None:
        await self._session.execute(
            update(NotificationOutbox)
            .where(NotificationOutbox.id == outbox_id)
            .values(status="skipped", updated_at=func.now())
        )

    async def record_failure(self, outbox_id: uuid.UUID, error_code: str) -> None:
        row = await self._session.get(NotificationOutbox, outbox_id)
        if row is None:
            return
        attempts = row.attempts + 1
        row.attempts = attempts
        row.last_error_code = error_code[:120]
        row.updated_at = datetime.now(UTC)
        if attempts >= 10:
            row.status = "failed"
        else:
            row.available_at = datetime.now(UTC) + timedelta(seconds=min(2**attempts, 60))
