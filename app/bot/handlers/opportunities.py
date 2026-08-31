from __future__ import annotations

import logging
import uuid

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.services import (
    filters_confirmation_keyboard,
    filters_menu_keyboard,
    format_collected_message,
    format_filter_list,
    message_keyboard,
    parse_filter_command,
    parse_filter_values,
)
from app.database.models import BotUser, BotUserKeyword
from app.database.repositories import BotFeatureRepository, BotUserRepository

logger = logging.getLogger(__name__)


class FilterStates(StatesGroup):
    waiting_for_values = State()
    waiting_for_confirmation = State()


async def _registered_user(session: AsyncSession, telegram_user_id: int) -> BotUser | None:
    return await BotUserRepository(session).get_by_telegram_id(telegram_user_id)


def create_opportunities_router(
    session_factory: async_sessionmaker[AsyncSession],
    owner_telegram_id: int,
) -> Router:
    router = Router(name="opportunities")
    router.message.filter(F.chat.type == "private")
    router.message.filter(F.from_user.id == owner_telegram_id)
    router.callback_query.filter(F.from_user.id == owner_telegram_id)

    @router.message(Command("filters"))
    async def filters_command(message: Message, command: CommandObject, state: FSMContext) -> None:
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
                await state.clear()
                await message.answer(
                    _filters_menu_text(current),
                    reply_markup=filters_menu_keyboard(),
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
                inserted = await repository.add_keywords(user.id, new_keywords)
                await session.commit()
                await message.answer(f"تمت إضافة {inserted} فلتر. استخدم /latest لعرض النتائج.")
                return

            removed = 0
            for _, normalized in parsed.keywords:
                removed += int(await repository.remove_keyword(user.id, normalized))
            await session.commit()
            await message.answer(f"تم حذف {removed} فلتر.")

    @router.callback_query(F.data == "filters:add:start")
    async def start_filter_entry(callback: CallbackQuery, state: FSMContext) -> None:
        async with session_factory() as session:
            user = await _registered_user(session, callback.from_user.id)
        if user is None:
            await callback.answer("استخدم /start أولًا.", show_alert=True)
            return

        await state.clear()
        await state.set_state(FilterStates.waiting_for_values)
        await callback.answer()
        await callback.bot.send_message(
            callback.from_user.id,
            "اكتب الكلمات أو الجمل التي تريد إضافتها في رسالة واحدة.\n\n"
            "افصل بينها بسطر جديد أو فاصلة , أو فاصلة عربية ،\n\n"
            "مثال:\nPython developer\n.NET\nتصميم مواقع",
        )

    @router.message(FilterStates.waiting_for_values, F.text)
    async def preview_filter_values(message: Message, state: FSMContext) -> None:
        if message.from_user is None or message.text is None:
            return
        try:
            parsed_values = parse_filter_values(message.text)
        except ValueError as exc:
            await message.answer(str(exc))
            return

        async with session_factory() as session:
            user = await _registered_user(session, message.from_user.id)
            if user is None:
                await state.clear()
                await message.answer("استخدم /start أولًا.")
                return
            current = await BotFeatureRepository(session).list_keywords(user.id)

        existing = {item.normalized_keyword for item in current}
        new_values = [item for item in parsed_values if item[1] not in existing]
        if not new_values:
            await message.answer("كل الكلمات موجودة بالفعل. أرسل كلمات أو جمل أخرى.")
            return

        await state.update_data(filter_draft=message.text)
        await state.set_state(FilterStates.waiting_for_confirmation)
        preview = format_filter_list([keyword for keyword, _ in new_values])
        await message.answer(
            f"سيتم إضافة {len(new_values)} فلتر:\n\n{preview}\n\nاضغط Add لتطبيقهم.",
            reply_markup=filters_confirmation_keyboard(),
        )

    @router.message(FilterStates.waiting_for_values)
    async def reject_non_text_filter_values(message: Message) -> None:
        await message.answer("أرسل الكلمات والجمل كنص في رسالة واحدة.")

    @router.callback_query(F.data == "filters:add:confirm")
    async def confirm_filter_values(callback: CallbackQuery, state: FSMContext) -> None:
        if await state.get_state() != FilterStates.waiting_for_confirmation.state:
            await callback.answer("انتهت هذه العملية. افتح /filters من جديد.", show_alert=True)
            return
        data = await state.get_data()
        draft = data.get("filter_draft")
        if not isinstance(draft, str):
            await state.clear()
            await callback.answer("انتهت هذه العملية. حاول من جديد.", show_alert=True)
            return

        parsed_values = parse_filter_values(draft)
        async with session_factory() as session:
            user = await _registered_user(session, callback.from_user.id)
            if user is None:
                await state.clear()
                await callback.answer("استخدم /start أولًا.", show_alert=True)
                return
            repository = BotFeatureRepository(session)
            current = await repository.list_keywords(user.id)
            existing = {item.normalized_keyword for item in current}
            new_values = [item for item in parsed_values if item[1] not in existing]
            inserted = await repository.add_keywords(user.id, new_values)
            await session.commit()

        await state.clear()
        await callback.answer(f"تمت إضافة {inserted} فلتر.")
        await callback.bot.send_message(
            callback.from_user.id,
            f"تم تطبيق {inserted} فلتر بنجاح. استخدم /latest لعرض النتائج.",
        )

    @router.callback_query(F.data == "filters:add:cancel")
    async def cancel_filter_values(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.answer("تم الإلغاء.")
        await callback.bot.send_message(
            callback.from_user.id,
            "تم إلغاء الإضافة ولم يتم حفظ أي فلتر.",
        )

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


def _filters_menu_text(current: list[BotUserKeyword]) -> str:
    if not current:
        return "لا توجد فلاتر حاليًا.\n\nاضغط Add لإضافة الكلمات أو الجمل التي تريدها."
    values = format_filter_list([item.keyword for item in current])
    return (
        f"فلاترك الحالية ({len(current)}):\n{values}\n\n"
        "اضغط Add لإضافة المزيد.\n"
        "للحذف: /filters remove الكلمة\n"
        "لحذف الكل: /filters clear"
    )


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
