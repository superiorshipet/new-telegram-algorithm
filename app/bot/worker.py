from aiogram import Bot, Dispatcher

from app.bot.handlers import create_registration_router
from app.common.config import get_settings
from app.common.logging import configure_logging
from app.database.session import Database


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    database = Database(settings)
    bot = Bot(token=settings.require_bot_token())
    dispatcher = Dispatcher()
    dispatcher.include_router(create_registration_router(database.session_factory))

    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            handle_signals=True,
            close_bot_session=True,
        )
    finally:
        await database.dispose()
