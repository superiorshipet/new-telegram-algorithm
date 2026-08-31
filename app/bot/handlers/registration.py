import logging

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.repositories import BotUserRepository

logger = logging.getLogger(__name__)


def create_registration_router(
    session_factory: async_sessionmaker[AsyncSession],
) -> Router:
    router = Router(name="registration")

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        if message.chat.type != ChatType.PRIVATE or message.from_user is None:
            await message.answer("Please open the bot in a private chat and send /start.")
            return

        async with session_factory() as session:
            await BotUserRepository(session).register(
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
            )
            await session.commit()

        logger.info(
            "bot_user_registered",
            extra={"telegram_user_id": message.from_user.id},
        )
        await message.answer(
            "Registration complete. You will be able to receive matching "
            "opportunities here when notification delivery is enabled."
        )

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(
            "/start — register or reactivate your account\n"
            "/help — show the currently available commands"
        )

    return router
