from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BotUserKeyword(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bot_user_keywords"
    __table_args__ = (
        UniqueConstraint(
            "bot_user_id",
            "normalized_keyword",
            name="uq_bot_user_keywords_user_normalized",
        ),
    )

    bot_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bot_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_keyword: Mapped[str] = mapped_column(String(100), nullable=False)
