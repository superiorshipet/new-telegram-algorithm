from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.database.models.collected_message import CollectedMessage


class TelegramGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "telegram_groups"

    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), index=True
    )

    messages: Mapped[list[CollectedMessage]] = relationship(back_populates="group")
