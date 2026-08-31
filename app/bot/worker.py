import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.bot.handlers import create_opportunities_router, create_registration_router
from app.bot.notifications import NotificationDispatcher
from app.common.config import get_settings
from app.common.logging import configure_logging
from app.database.session import Database


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    database = Database(settings)
    owner_telegram_id = settings.require_bot_owner_telegram_id()
    bot = Bot(token=settings.require_bot_token())
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(
        create_registration_router(database.session_factory, owner_telegram_id)
    )
    dispatcher.include_router(
        create_opportunities_router(database.session_factory, owner_telegram_id)
    )
    stop_event = asyncio.Event()
    notification_dispatcher = NotificationDispatcher(
        bot,
        database.session_factory,
        settings.sqlalchemy_database_url,
        owner_telegram_id,
    )
    notification_task = asyncio.create_task(
        notification_dispatcher.run(stop_event),
        name="notification-dispatcher",
    )

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Register or reactivate your account"),
                BotCommand(command="filters", description="Manage your interests and filters"),
                BotCommand(command="latest", description="View latest matching opportunities"),
                BotCommand(command="saved", description="View saved opportunities"),
                BotCommand(command="status", description="View your account status"),
                BotCommand(command="help", description="Show available commands"),
                BotCommand(command="stop", description="Pause notifications"),
            ]
        )
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            handle_signals=True,
            close_bot_session=False,
        )
    finally:
        stop_event.set()
        await asyncio.gather(notification_task, return_exceptions=True)
        await bot.session.close()
        await database.dispose()
