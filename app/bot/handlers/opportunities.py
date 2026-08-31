from __future__ import annotations

import logging
import uuid

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.services import (
    MAX_FILTERS_PER_USER,
    format_collected_message,
    message_keyboard,
    parse_filter_command,
)
from app.database.models import BotUser
from app.database.repositories import BotFeatureRepository, BotUserRepository

logger = logging.getLogger(__name__)


async def _registered_user(session: AsyncSession, telegram_user_id: int) -> BotUser | None:
    return await BotUserRepository(session).get_by_telegram_id(telegram_user_id)


def create_opportunities_router(
    session_factory: async_sessionmaker[AsyncSession],
) -> Router:
    router = Router(name="opportunities")
    router.message.filter(F.chat.type == "private")

    @router.message(Command("filters"))
    async def filters_command(message: Message, command: CommandObject) -> None:
        if message.from_user is None:
            return
        try:
            parsed = parse_filter_command(command.args)
        except ValueError as exc:
            await message.answer(str(exc))
            return

        async with session_factory() as session:
            user = await _registered_user(session, message.from_user.id)
            if user is None:
                await message.answer("سجّل حسابك أولًا باستخدام /start")
                return

            repository = BotFeatureRepository(session)
            current = await repository.list_keywords(user.id)

            if parsed.action == "list":
                if not current:
                    await message.answer(
                        "لا توجد فلاتر حاليًا.\nللإضافة: /filters add Python, .NET, تصميم مواقع"
                    )
                    return
                values = "\n".join(f"• {item.keyword}" for item in current)
                await message.answer(
                    f"فلاترك الحالية ({len(current)}/{MAX_FILTERS_PER_USER}):\n{values}\n\n"
                    "للحذف: /filters remove الكلمة\n"
                    "لحذف الكل: /filters clear"
                )
                return

            if parsed.action == "clear":
                removed = await repository.clear_keywords(user.id)
                await session.commit()
                await message.answer(f"تم حذف {removed} فلتر.")
                return

            if parsed.action == "add":
                existing = {item.normalized_keyword for item in current}
                new_keywords = [item for item in parsed.keywords if item[1] not in existing]
                if len(current) + len(new_keywords) > MAX_FILTERS_PER_USER:
                    await message.answer(
                        f"الحد الأقصى {MAX_FILTERS_PER_USER} فلتر. احذف فلترًا أولًا."
                    )
                    return
                inserted = await repository.add_keywords(user.id, new_keywords)
                await session.commit()
                await message.answer(f"تمت إضافة {inserted} فلتر. استخدم /latest لعرض النتائج.")
                return

            removed = 0
            for _, normalized in parsed.keywords:
                removed += int(await repository.remove_keyword(user.id, normalized))
            await session.commit()
            await message.answer(f"تم حذف {removed} فلتر.")

    @router.message(Command("latest"))
    async def latest_command(message: Message) -> None:
        if message.from_user is None:
            return
        async with session_factory() as session:
            user = await _registered_user(session, message.from_user.id)
            if user is None:
                await message.answer("سجّل حسابك أولًا باستخدام /start")
                return
            repository = BotFeatureRepository(session)
            keywords = await repository.list_keywords(user.id)
            results = await repository.latest_matching_messages(
                [item.normalized_keyword for item in keywords]
            )

        if not results:
            await message.answer("لا توجد فرص مطابقة حاليًا.")
            return
        if not keywords:
            await message.answer(
                "لا توجد فلاتر، لذلك أعرض أحدث الرسائل. استخدم /filters لإضافة اهتماماتك."
            )
        for result in results:
            await message.answer(
                format_collected_message(result),
                reply_markup=message_keyboard(result),
            )

    @router.message(Command("saved"))
    async def saved_command(message: Message) -> None:
        if message.from_user is None:
            return
        async with session_factory() as session:
            user = await _registered_user(session, message.from_user.id)
            if user is None:
                await message.answer("سجّل حسابك أولًا باستخدام /start")
                return
            results = await BotFeatureRepository(session).list_saved_messages(user.id)

        if not results:
            await message.answer("لا توجد رسائل محفوظة.")
            return
        for result in results:
            await message.answer(
                format_collected_message(result),
                reply_markup=message_keyboard(result, saved=True),
            )

    @router.message(Command("status"))
    async def status_command(message: Message) -> None:
        if message.from_user is None:
            return
        async with session_factory() as session:
            user = await _registered_user(session, message.from_user.id)
            if user is None:
                await message.answer("الحساب غير مسجل. استخدم /start")
                return
            counts = await BotFeatureRepository(session).get_counts(user.id)

        notification_status = "مفعلة" if user.is_active else "متوقفة"
        await message.answer(
            f"حالة الحساب: مسجل\n"
            f"الإشعارات: {notification_status}\n"
            f"عدد الفلاتر: {counts.keyword_count}\n"
            f"الرسائل المحفوظة: {counts.saved_count}"
        )

    @router.message(Command("stop"))
    async def stop_command(message: Message) -> None:
        if message.from_user is None:
            return
        async with session_factory() as session:
            updated = await BotUserRepository(session).set_notifications_active(
                message.from_user.id, active=False
            )
            await session.commit()
        if not updated:
            await message.answer("الحساب غير مسجل. استخدم /start")
            return
        await message.answer(
            "تم إيقاف الإشعارات. يمكنك استخدام الأوامر يدويًا، و/start يعيد تفعيلها."
        )

    @router.callback_query(F.data.startswith("save:"))
    async def save_callback(callback: CallbackQuery) -> None:
        await _change_saved_state(callback, session_factory, save=True)

    @router.callback_query(F.data.startswith("unsave:"))
    async def unsave_callback(callback: CallbackQuery) -> None:
        await _change_saved_state(callback, session_factory, save=False)

    return router


async def _change_saved_state(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    save: bool,
) -> None:
    data = callback.data or ""
    try:
        message_id = uuid.UUID(data.partition(":")[2])
    except ValueError:
        await callback.answer("طلب غير صالح.", show_alert=True)
        return

    async with session_factory() as session:
        user = await _registered_user(session, callback.from_user.id)
        if user is None:
            await callback.answer("استخدم /start أولًا.", show_alert=True)
            return
        repository = BotFeatureRepository(session)
        if save:
            result = await repository.save_message(user.id, message_id)
            await session.commit()
            responses = {
                "saved": "تم الحفظ.",
                "already_saved": "الرسالة محفوظة بالفعل.",
                "not_found": "الرسالة لم تعد موجودة.",
            }
            await callback.answer(responses[result])
        else:
            removed = await repository.remove_saved_message(user.id, message_id)
            await session.commit()
            await callback.answer("تمت الإزالة." if removed else "الرسالة غير محفوظة.")
            if removed and callback.message:
                await callback.message.edit_reply_markup(reply_markup=None)

    logger.info(
        "saved_message_changed",
        extra={"telegram_user_id": callback.from_user.id, "saved": save},
    )
