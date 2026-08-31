from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.database.models.source_account import SourceAccount
    from app.database.models.telegram_group import TelegramGroup


class CollectedMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "collected_messages"
    __table_args__ = (
        UniqueConstraint(
            "telegram_group_id",
            "telegram_message_id",
            name="uq_collected_messages_group_message",
        ),
        Index("ix_collected_messages_content_hash", "content_hash"),
        Index("ix_collected_messages_message_date", "message_date"),
    )

    telegram_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("telegram_groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    sender_name: Mapped[str | None] = mapped_column(String(255))
    sender_username: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    original_message_link: Mapped[str | None] = mapped_column(Text)
    message_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("now()")
    )
    source_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    preliminary_score: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("0")
    )

    group: Mapped[TelegramGroup] = relationship(back_populates="messages")
    source_account: Mapped[SourceAccount] = relationship(back_populates="messages")
