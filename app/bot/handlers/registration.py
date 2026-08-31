from __future__ import annotations

import hmac
import logging
import uuid
from contextlib import suppress

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.services import DEFAULT_FILTER_VERSION, default_filter_values_since
from app.database.models import BotAccessGrant
from app.database.repositories import (
    BotAccessRepository,
    BotFeatureRepository,
    BotUserRepository,
)
from app.database.repositories.bot_access import AccessSubject, parse_access_subject

logger = logging.getLogger(__name__)


class AccessStates(StatesGroup):
    waiting_for_subject = State()
    waiting_for_password = State()


def owner_access_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ منح صلاحية", callback_data="access:add")],
            [InlineKeyboardButton(text="👥 الصلاحيات الحالية", callback_data="access:list")],
        ]
    )


def access_list_keyboard(grants: list[BotAccessGrant]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"إلغاء @{grant.subject_value}"
                    if grant.subject_type == "username"
                    else f"إلغاء {grant.subject_value}"
                ),
                callback_data=f"access:revoke:{grant.id}",
            )
        ]
        for grant in grants
    ]
    rows.append([InlineKeyboardButton(text="➕ منح صلاحية", callback_data="access:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_registration_router(
    session_factory: async_sessionmaker[AsyncSession],
    owner_telegram_id: int,
    access_password: str,
) -> Router:
    router = Router(name="registration")

    async def register_user(message: Message) -> int:
        assert message.from_user is not None
        async with session_factory() as session:
            user_repository = BotUserRepository(session)
            user = await user_repository.register(
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
            )
            default_count = 0
            if user.default_filter_version < DEFAULT_FILTER_VERSION:
                default_count = await BotFeatureRepository(session).add_keywords(
                    user.id,
                    default_filter_values_since(user.default_filter_version),
                )
                await user_repository.mark_default_filters_seeded(user.id, DEFAULT_FILTER_VERSION)
            await session.commit()
        return default_count

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        if message.chat.type != ChatType.PRIVATE or message.from_user is None:
            await message.answer("Please open the bot in a private chat and send /start.")
            return

        is_owner = message.from_user.id == owner_telegram_id
        if not is_owner:
            async with session_factory() as session:
                authorized = await BotAccessRepository(session).authorize_and_bind(
                    message.from_user.id,
                    message.from_user.username,
                )
                if authorized:
                    await session.commit()
            if not authorized:
                logger.warning(
                    "unauthorized_bot_access",
                    extra={"telegram_user_id": message.from_user.id},
                )
                await message.answer("هذا البوت خاص وغير متاح لهذا الحساب.")
                return

        default_count = await register_user(message)
        logger.info(
            "bot_user_registered",
            extra={"telegram_user_id": message.from_user.id},
        )
        default_message = f" وتمت إضافة {default_count} فلتر افتراضي." if default_count else ""
        await message.answer(
            f"تم تسجيل حسابك وتفعيل الإشعارات.{default_message} "
            "استخدم /filters لإدارة اهتماماتك.",
            reply_markup=owner_access_keyboard() if is_owner else None,
        )

    @router.message(Command("access"))
    async def access_command(message: Message, state: FSMContext) -> None:
        if message.from_user is None or message.from_user.id != owner_telegram_id:
            await message.answer("إدارة الصلاحيات متاحة للمالك فقط.")
            return
        await state.clear()
        await message.answer("إدارة المستخدمين المصرح لهم:", reply_markup=owner_access_keyboard())

    @router.callback_query(F.data == "access:add")
    async def start_access_grant(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.from_user.id != owner_telegram_id:
            await callback.answer("هذا الخيار للمالك فقط.", show_alert=True)
            return
        await state.clear()
        await state.set_state(AccessStates.waiting_for_subject)
        await callback.answer()
        await callback.bot.send_message(
            callback.from_user.id,
            "أرسل Telegram User ID الرقمي أو Username مثل @username.\n"
            "لا يمكن منح الإذن برقم الهاتف.",
        )

    @router.message(AccessStates.waiting_for_subject, F.text)
    async def receive_access_subject(message: Message, state: FSMContext) -> None:
        if message.from_user is None or message.from_user.id != owner_telegram_id:
            await state.clear()
            return
        try:
            subject = parse_access_subject(message.text or "")
        except ValueError as exc:
            await message.answer(str(exc))
            return
        await state.update_data(
            access_subject_type=subject.subject_type,
            access_subject_value=subject.subject_value,
        )
        await state.set_state(AccessStates.waiting_for_password)
        await message.answer("أدخل كلمة سر إدارة الصلاحيات لتأكيد الإذن:")

    @router.message(AccessStates.waiting_for_password, F.text)
    async def confirm_access_grant(message: Message, state: FSMContext) -> None:
        if message.from_user is None or message.from_user.id != owner_telegram_id:
            await state.clear()
            return
        supplied_password = message.text or ""
        with suppress(TelegramBadRequest, TelegramForbiddenError):
            await message.delete()
        if not hmac.compare_digest(supplied_password, access_password):
            await state.clear()
            logger.warning("access_grant_password_rejected")
            await message.answer("كلمة السر غير صحيحة. لم يتم منح أي صلاحية.")
            return

        data = await state.get_data()
        subject_type = data.get("access_subject_type")
        subject_value = data.get("access_subject_value")
        if not isinstance(subject_type, str) or not isinstance(subject_value, str):
            await state.clear()
            await message.answer("انتهت العملية. افتح /access وحاول مرة أخرى.")
            return
        subject = AccessSubject(subject_type, subject_value)
        async with session_factory() as session:
            await BotAccessRepository(session).grant(subject, owner_telegram_id)
            await session.commit()
        await state.clear()
        logger.info("bot_access_granted", extra={"subject_type": subject.subject_type})
        await message.answer(
            f"تم منح الصلاحية إلى {subject.display}. يمكنه الآن إرسال /start.",
            reply_markup=owner_access_keyboard(),
        )

    @router.callback_query(F.data == "access:list")
    async def list_access_grants(callback: CallbackQuery) -> None:
        if callback.from_user.id != owner_telegram_id:
            await callback.answer("هذا الخيار للمالك فقط.", show_alert=True)
            return
        async with session_factory() as session:
            grants = await BotAccessRepository(session).list_active()
        await callback.answer()
        text = "لا توجد صلاحيات إضافية." if not grants else "المستخدمون المصرح لهم:"
        await callback.bot.send_message(
            callback.from_user.id,
            text,
            reply_markup=access_list_keyboard(grants),
        )

    @router.callback_query(F.data.startswith("access:revoke:"))
    async def revoke_access(callback: CallbackQuery) -> None:
        if callback.from_user.id != owner_telegram_id:
            await callback.answer("هذا الخيار للمالك فقط.", show_alert=True)
            return
        try:
            grant_id = uuid.UUID((callback.data or "").rsplit(":", 1)[-1])
        except ValueError:
            await callback.answer("طلب غير صالح.", show_alert=True)
            return
        async with session_factory() as session:
            revoked = await BotAccessRepository(session).revoke(grant_id)
            await session.commit()
        await callback.answer("تم إلغاء الصلاحية." if revoked else "الصلاحية غير موجودة.")
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        owner_help = (
            "\n/access — إدارة المستخدمين المصرح لهم"
            if message.from_user and message.from_user.id == owner_telegram_id
            else ""
        )
        await message.answer(
            "/start — تسجيل الحساب أو إعادة تفعيله\n"
            "/filters — إدارة كلمات وعبارات البحث\n"
            "/latest — أحدث الفرص المطابقة\n"
            "/saved — الرسائل المحفوظة\n"
            "/status — حالة الحساب\n"
            "/stop — إيقاف الإشعارات\n"
            f"/help — عرض الأوامر{owner_help}"
        )

    return router
