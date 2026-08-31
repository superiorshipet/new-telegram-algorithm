from __future__ import annotations

import uuid
import re
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BotAccessGrant, BotUser


@dataclass(frozen=True, slots=True)
class AccessSubject:
    subject_type: str
    subject_value: str

    @property
    def display(self) -> str:
        return (
            f"@{self.subject_value}" if self.subject_type == "username" else self.subject_value
        )


def parse_access_subject(raw_value: str) -> AccessSubject:
    value = raw_value.strip()
    if value.startswith("@"):
        username = value[1:].strip().casefold()
        if re.fullmatch(r"[a-z0-9_]{5,32}", username) is None:
            raise ValueError("اكتب Username صحيحًا مثل @username")
        return AccessSubject("username", username)
    if value.isdecimal() and int(value) > 0:
        return AccessSubject("telegram_id", str(int(value)))
    raise ValueError("اكتب Telegram User ID رقميًا أو Username يبدأ بعلامة @")


class BotAccessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def grant(self, subject: AccessSubject, granted_by: int) -> BotAccessGrant:
        statement = insert(BotAccessGrant).values(
            subject_type=subject.subject_type,
            subject_value=subject.subject_value,
            granted_by_telegram_user_id=granted_by,
            is_active=True,
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_bot_access_grants_subject",
            set_={
                "granted_by_telegram_user_id": statement.excluded.granted_by_telegram_user_id,
                "is_active": True,
            },
        )
        return (await self._session.execute(statement.returning(BotAccessGrant))).scalar_one()

    async def authorize_and_bind(self, telegram_user_id: int, username: str | None) -> bool:
        id_value = str(telegram_user_id)
        id_grant = await self._session.scalar(
            select(BotAccessGrant)
            .where(BotAccessGrant.subject_type == "telegram_id")
            .where(BotAccessGrant.subject_value == id_value)
            .where(BotAccessGrant.is_active.is_(True))
        )
        if id_grant is not None:
            return True

        normalized_username = (username or "").strip().lstrip("@").casefold()
        if not normalized_username:
            return False
        username_grant = await self._session.scalar(
            select(BotAccessGrant)
            .where(BotAccessGrant.subject_type == "username")
            .where(BotAccessGrant.subject_value == normalized_username)
            .where(BotAccessGrant.is_active.is_(True))
            .with_for_update()
        )
        if username_grant is None:
            return False

        await self.grant(
            AccessSubject("telegram_id", id_value),
            username_grant.granted_by_telegram_user_id,
        )
        username_grant.is_active = False
        return True

    async def list_active(self) -> list[BotAccessGrant]:
        result = await self._session.scalars(
            select(BotAccessGrant)
            .where(BotAccessGrant.is_active.is_(True))
            .order_by(BotAccessGrant.created_at, BotAccessGrant.subject_value)
        )
        return list(result)

    async def revoke(self, grant_id: uuid.UUID) -> bool:
        grant = await self._session.get(BotAccessGrant, grant_id)
        if grant is None or not grant.is_active:
            return False
        grant.is_active = False
        if grant.subject_type == "telegram_id":
            await self._session.execute(
                update(BotUser)
                .where(BotUser.telegram_user_id == int(grant.subject_value))
                .values(is_active=False)
            )
        return True
