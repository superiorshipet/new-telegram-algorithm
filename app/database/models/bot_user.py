from sqlalchemy import BigInteger, Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BotUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bot_users"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), index=True
    )
