from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, UUIDPrimaryKeyMixin


class MessageObservation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "message_observations"
    __table_args__ = (
        UniqueConstraint(
            "collected_message_id",
            "source_account_id",
            name="uq_message_observations_message_source",
        ),
    )

    collected_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collected_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
