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
from app.database.models import BotAccessGrant, BotUser
from app.database.repositories import (
    BotAccessRepository,
    BotFeatureRepository,
    BotUserRepository,
)
from app.database.repositories.bot_access import AccessSubject, parse_access_subject

logger = logging.getLogger(__name__)


class AccessStates(StatesGroup):
    waiting_for_subject = State()
    waiting_for_role = State()
    waiting_for_password = State()


def owner_access_keyboard(*, allow_admin_management: bool = True) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="➕ منح صلاحية", callback_data="access:add")],
        [InlineKeyboardButton(text="👥 الصلاحيات الحالية", callback_data="access:list")],
    ]
    if allow_admin_management:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⭐ ترقية حساب موجود لمشرف",
                    callback_data="access:promote",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="📥 حسابات التجميع", callback_data="accounts:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def promotable_users_keyboard(users: list[BotUser]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for user in users:
        identity = f"@{user.username}" if user.username else str(user.telegram_user_id)
        label = " — ".join(part for part in (user.first_name, identity) if part)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"⭐ {label}",
                    callback_data=f"access:promote:{user.telegram_user_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def access_role_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👤 مستخدم عادي",
                    callback_data="access:role:user",
                ),
                InlineKeyboardButton(
                    text="🛡 مشرف",
                    callback_data="access:role:admin",
                ),
            ]
        ]
    )


def access_list_keyboard(
    grants: list[BotAccessGrant],
    *,
    allow_admin_management: bool,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"إلغاء @{grant.subject_value}"
                    if grant.subject_type == "username"
                    else f"إلغاء {grant.subject_value}"
                )
                + (" (مشرف)" if grant.is_access_admin else ""),
                callback_data=f"access:revoke:{grant.id}",
            )
        ]
        for grant in grants
        if allow_admin_management or not grant.is_access_admin
    ]
    rows.append([InlineKeyboardButton(text="➕ منح صلاحية", callback_data="access:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def create_registration_router(
    session_factory: async_sessionmaker[AsyncSession],
    owner_telegram_id: int,
    access_password: str,
) -> Router:
    router = Router(name="registration")

    async def can_manage_access(telegram_user_id: int) -> bool:
        if telegram_user_id == owner_telegram_id:
            return True
        async with session_factory() as session:
            user = await BotUserRepository(session).get_by_telegram_id(telegram_user_id)
        return bool(user and user.is_active and user.is_access_admin)

    async def register_user(message: Message, *, is_access_admin: bool) -> int:
        assert message.from_user is not None
        async with session_factory() as session:
            user_repository = BotUserRepository(session)
            user = await user_repository.register(
                telegram_user_id=message.from_user.id,
                telegram_chat_id=message.chat.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                is_access_admin=is_access_admin,
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

    async def save_access_grant(
        message: Message,
        state: FSMContext,
        subject: AccessSubject,
        *,
        is_access_admin: bool,
    ) -> None:
        async with session_factory() as session:
            await BotAccessRepository(session).grant(
                subject,
                message.from_user.id,
                is_access_admin=is_access_admin,
            )
            await session.commit()
        await state.clear()
        logger.info(
            "bot_access_granted",
            extra={
                "subject_type": subject.subject_type,
                "is_access_admin": is_access_admin,
            },
        )
        role_text = "مشرف" if is_access_admin else "مستخدم"
        await message.answer(
            f"تمت إضافة {subject.display} كـ{role_text}. يمكنه الآن إرسال /start.",
            reply_markup=owner_access_keyboard(
                allow_admin_management=message.from_user.id == owner_telegram_id
            ),
        )

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        if message.chat.type != ChatType.PRIVATE or message.from_user is None:
            await message.answer("Please open the bot in a private chat and send /start.")
            return

        is_owner = message.from_user.id == owner_telegram_id
        access_grant = None
        if not is_owner:
            async with session_factory() as session:
                access_grant = await BotAccessRepository(session).authorize_and_bind(
                    message.from_user.id,
                    message.from_user.username,
                )
                if access_grant is not None:
                    await session.commit()
            if access_grant is None:
                logger.warning(
                    "unauthorized_bot_access",
                    extra={"telegram_user_id": message.from_user.id},
                )
                await message.answer("هذا البوت خاص وغير متاح لهذا الحساب.")
                return

        is_access_admin = is_owner or bool(access_grant and access_grant.is_access_admin)
        default_count = await register_user(message, is_access_admin=is_access_admin)
        logger.info(
            "bot_user_registered",
            extra={"telegram_user_id": message.from_user.id},
        )
        default_message = f" وتمت إضافة {default_count} فلتر افتراضي." if default_count else ""
        await message.answer(
            f"تم تسجيل حسابك وتفعيل الإشعارات.{default_message} "
            "استخدم /filters لإدارة اهتماماتك.",
            reply_markup=(
                owner_access_keyboard(allow_admin_management=is_owner)
                if is_access_admin
                else None
            ),
        )

    @router.message(Command("access"))
    async def access_command(message: Message, state: FSMContext) -> None:
        if message.from_user is None or not await can_manage_access(message.from_user.id):
            await message.answer("إدارة الصلاحيات متاحة للمشرفين فقط.")
            return
        await state.clear()
        await message.answer(
            "إدارة المستخدمين المصرح لهم:",
            reply_markup=owner_access_keyboard(
                allow_admin_management=message.from_user.id == owner_telegram_id
            ),
        )

    @router.callback_query(F.data == "access:promote")
    async def list_promotable_users(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.from_user.id != owner_telegram_id:
            await callback.answer("ترقية المشرفين متاحة للمالك فقط.", show_alert=True)
            return
        async with session_factory() as session:
            users = await BotUserRepository(session).list_promotable()
        await state.clear()
        await callback.answer()
        if not users:
            await callback.bot.send_message(
                callback.from_user.id,
                "لا توجد حسابات عادية مسجلة متاحة للترقية.",
            )
            return
        await callback.bot.send_message(
            callback.from_user.id,
            "اختر الحساب الذي تريد ترقيته إلى مشرف:",
            reply_markup=promotable_users_keyboard(users),
        )

    @router.callback_query(F.data.startswith("access:promote:"))
    async def select_user_promotion(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.from_user.id != owner_telegram_id:
            await callback.answer("ترقية المشرفين متاحة للمالك فقط.", show_alert=True)
            return
        try:
            telegram_user_id = int((callback.data or "").rsplit(":", 1)[-1])
        except ValueError:
            await callback.answer("حساب غير صالح.", show_alert=True)
            return
        async with session_factory() as session:
            user = await BotUserRepository(session).get_by_telegram_id(telegram_user_id)
        if user is None or user.is_access_admin:
            await callback.answer("الحساب غير متاح للترقية.", show_alert=True)
            return
        await state.clear()
        await state.update_data(
            access_subject_type="telegram_id",
            access_subject_value=str(telegram_user_id),
            access_is_admin=True,
        )
        await state.set_state(AccessStates.waiting_for_password)
        await callback.answer()
        await callback.bot.send_message(
            callback.from_user.id,
            "أدخل كلمة سر إدارة الصلاحيات لتأكيد ترقية الحساب إلى مشرف:",
        )

    @router.callback_query(F.data == "access:add")
    async def start_access_grant(callback: CallbackQuery, state: FSMContext) -> None:
        if not await can_manage_access(callback.from_user.id):
            await callback.answer("هذا الخيار للمشرفين فقط.", show_alert=True)
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
        if message.from_user is None or not await can_manage_access(message.from_user.id):
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
        if message.from_user.id == owner_telegram_id:
            await state.set_state(AccessStates.waiting_for_role)
            await message.answer(
                "اختر نوع الصلاحية:",
                reply_markup=access_role_keyboard(),
            )
            return

        await save_access_grant(
            message,
            state,
            subject,
            is_access_admin=False,
        )

    @router.callback_query(AccessStates.waiting_for_role, F.data.startswith("access:role:"))
    async def select_access_role(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.from_user.id != owner_telegram_id:
            await state.clear()
            await callback.answer("تعيين المشرفين متاح للمالك فقط.", show_alert=True)
            return
        role = (callback.data or "").rsplit(":", 1)[-1]
        if role not in {"user", "admin"}:
            await callback.answer("نوع صلاحية غير صالح.", show_alert=True)
            return
        await state.update_data(access_is_admin=role == "admin")
        await state.set_state(AccessStates.waiting_for_password)
        await callback.answer()
        await callback.bot.send_message(
            callback.from_user.id,
            "أدخل كلمة سر إدارة الصلاحيات لتأكيد الإذن:",
        )

    @router.message(AccessStates.waiting_for_password, F.text)
    async def confirm_access_grant(message: Message, state: FSMContext) -> None:
        if message.from_user is None or not await can_manage_access(message.from_user.id):
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
        is_access_admin = data.get("access_is_admin", False)
        if not isinstance(subject_type, str) or not isinstance(subject_value, str):
            await state.clear()
            await message.answer("انتهت العملية. افتح /access وحاول مرة أخرى.")
            return
        subject = AccessSubject(subject_type, subject_value)
        await save_access_grant(
            message,
            state,
            subject,
            is_access_admin=bool(is_access_admin),
        )

    @router.callback_query(F.data == "access:list")
    async def list_access_grants(callback: CallbackQuery) -> None:
        if not await can_manage_access(callback.from_user.id):
            await callback.answer("هذا الخيار للمشرفين فقط.", show_alert=True)
            return
        async with session_factory() as session:
            grants = await BotAccessRepository(session).list_active()
        await callback.answer()
        text = "لا توجد صلاحيات إضافية." if not grants else "المستخدمون المصرح لهم:"
        await callback.bot.send_message(
            callback.from_user.id,
            text,
            reply_markup=access_list_keyboard(
                grants,
                allow_admin_management=callback.from_user.id == owner_telegram_id,
            ),
        )

    @router.callback_query(F.data.startswith("access:revoke:"))
    async def revoke_access(callback: CallbackQuery) -> None:
        if not await can_manage_access(callback.from_user.id):
            await callback.answer("هذا الخيار للمشرفين فقط.", show_alert=True)
            return
        try:
            grant_id = uuid.UUID((callback.data or "").rsplit(":", 1)[-1])
        except ValueError:
            await callback.answer("طلب غير صالح.", show_alert=True)
            return
        async with session_factory() as session:
            grant = await session.get(BotAccessGrant, grant_id)
            if (
                grant is not None
                and grant.is_access_admin
                and callback.from_user.id != owner_telegram_id
            ):
                await callback.answer("إلغاء المشرفين متاح للمالك فقط.", show_alert=True)
                return
            revoked = await BotAccessRepository(session).revoke(grant_id)
            await session.commit()
        await callback.answer("تم إلغاء الصلاحية." if revoked else "الصلاحية غير موجودة.")
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        management_help = ""
        if message.from_user and await can_manage_access(message.from_user.id):
            management_help = (
                "\n/access — إدارة المستخدمين المصرح لهم"
                "\n/accounts — إدارة حسابات التجميع"
            )
        await message.answer(
            "/start — تسجيل الحساب أو إعادة تفعيله\n"
            "/filters — إدارة كلمات وعبارات البحث\n"
            "/latest — أحدث الفرص المطابقة\n"
            "/saved — الرسائل المحفوظة\n"
            "/status — حالة الحساب\n"
            "/stop — إيقاف الإشعارات\n"
            f"/help — عرض الأوامر{management_help}"
        )

    return router
