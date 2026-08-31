from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.database.models.collected_message import CollectedMessage


class SourceAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_accounts"

    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    phone_number_masked: Mapped[str | None] = mapped_column(String(40))
    session_string_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_id_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_hash_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'pending'")
    )
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    flood_wait_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list[CollectedMessage]] = relationship(back_populates="source_account")
