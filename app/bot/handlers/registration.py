import logging

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.services import default_filter_values
from app.database.repositories import BotFeatureRepository, BotUserRepository

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
            user_repository = BotUserRepository(session)
            user = await user_repository.register(
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
            )
            default_count = 0
            if not user.default_filters_seeded:
                default_count = await BotFeatureRepository(session).add_keywords(
                    user.id, default_filter_values()
                )
                await user_repository.mark_default_filters_seeded(user.id)
            await session.commit()

        logger.info(
            "bot_user_registered",
            extra={"telegram_user_id": message.from_user.id},
        )
        default_message = (
            f" وتمت إضافة {default_count} فلتر افتراضي." if default_count else ""
        )
        await message.answer(
            "تم تسجيل حسابك وتفعيل الإشعارات."
            f"{default_message} استخدم /filters لإدارة اهتماماتك."
        )

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(
            "/start — تسجيل الحساب أو إعادة تفعيله\n"
            "/filters — إدارة كلمات وعبارات البحث\n"
            "/latest — أحدث الفرص المطابقة\n"
            "/saved — الرسائل المحفوظة\n"
            "/status — حالة الحساب\n"
            "/stop — إيقاف الإشعارات\n"
            "/help — عرض الأوامر"
        )

    return router
