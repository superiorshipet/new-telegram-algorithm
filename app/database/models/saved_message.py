from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SavedMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "saved_messages"
    __table_args__ = (
        UniqueConstraint(
            "bot_user_id",
            "collected_message_id",
            name="uq_saved_messages_user_message",
        ),
    )

    bot_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bot_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collected_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collected_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
