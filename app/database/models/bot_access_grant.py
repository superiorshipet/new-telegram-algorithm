from sqlalchemy import BigInteger, Boolean, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BotAccessGrant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bot_access_grants"
    __table_args__ = (
        UniqueConstraint("subject_type", "subject_value", name="uq_bot_access_grants_subject"),
    )

    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_value: Mapped[str] = mapped_column(String(255), nullable=False)
    granted_by_telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), index=True
    )
    is_access_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
