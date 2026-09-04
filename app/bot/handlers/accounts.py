from __future__ import annotations

import asyncio
import io
import logging
import re
import uuid

import qrcode
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

from app.common.crypto import SecretCipher
from app.database.models import SourceAccount
from app.database.repositories import (
    MAX_ACTIVE_SOURCE_ACCOUNTS,
    BotUserRepository,
    SourceAccountRepository,
)

logger = logging.getLogger(__name__)
_PHONE_PATTERN = re.compile(r"^\+[1-9]\d{6,14}$")


class SourceAccountStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_method = State()
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()


def accounts_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ إضافة حساب", callback_data="accounts:add")],
            [InlineKeyboardButton(text="👤 إدارة الحسابات", callback_data="accounts:list")],
        ]
    )


def login_method_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📷 QR آمن", callback_data="accounts:login:qr"),
                InlineKeyboardButton(
                    text="📱 رقم الهاتف والكود",
                    callback_data="accounts:login:phone",
                ),
            ],
            [InlineKeyboardButton(text="إلغاء", callback_data="accounts:cancel")],
        ]
    )


def accounts_list_keyboard(accounts: list[SourceAccount]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for account in accounts:
        action = "disable" if account.is_active else "enable"
        action_text = "🔴 إيقاف" if account.is_active else "🟢 تشغيل"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{action_text} — {account.name}",
                    callback_data=f"accounts:{action}:{account.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ إضافة حساب", callback_data="accounts:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    if len(phone) <= 4:
        return "*" * len(phone)
    return f"{'*' * (len(phone) - 4)}{phone[-4:]}"


def format_accounts(accounts: list[SourceAccount]) -> str:
    if not accounts:
        return "لا توجد حسابات تجميع مضافة."
    active_count = sum(account.is_active for account in accounts)
    lines = [
        f"حسابات التجميع: {active_count}/{MAX_ACTIVE_SOURCE_ACCOUNTS} نشطة",
        "",
    ]
    for account in accounts:
        active = "يعمل" if account.is_active else "متوقف"
        lines.append(f"• {account.name} — {active} — الحالة: {account.status}")
    return "\n".join(lines)


def build_qr_png(value: str) -> bytes:
    image = qrcode.make(value)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def create_accounts_router(
    session_factory: async_sessionmaker[AsyncSession],
    owner_telegram_id: int,
    cipher: SecretCipher,
    api_id: int,
    api_hash: str,
) -> Router:
    router = Router(name="source-accounts")
    router.message.filter(F.chat.type == "private")
    qr_tasks: dict[int, asyncio.Task[None]] = {}

    async def can_manage(telegram_user_id: int) -> bool:
        if telegram_user_id == owner_telegram_id:
            return True
        async with session_factory() as session:
            user = await BotUserRepository(session).get_by_telegram_id(telegram_user_id)
        return bool(user and user.is_active and user.is_access_admin)

    async def require_manager(event: Message | CallbackQuery) -> bool:
        telegram_user_id = event.from_user.id if event.from_user else 0
        if await can_manage(telegram_user_id):
            return True
        if isinstance(event, CallbackQuery):
            await event.answer("إدارة الحسابات متاحة للمشرفين فقط.", show_alert=True)
        else:
            await event.answer("إدارة الحسابات متاحة للمشرفين فقط.")
        return False

    async def delete_sensitive_message(message: Message) -> None:
        try:
            await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError):
            pass

    async def persist_authenticated_client(
        client: TelegramClient,
        *,
        account_name: str,
    ) -> str:
        if not await client.is_user_authorized():
            return "unauthorized"
        session_string = client.session.save()
        if not session_string:
            return "unauthorized"
        me = await client.get_me()
        async with session_factory() as session:
            result = await SourceAccountRepository(session).save_authenticated(
                name=account_name,
                phone_number_masked=mask_phone(getattr(me, "phone", None)),
                session_string_encrypted=cipher.encrypt(session_string),
                api_id_encrypted=cipher.encrypt(str(api_id)),
                api_hash_encrypted=cipher.encrypt(api_hash),
            )
            await session.commit()
        return "limit_reached" if result.limit_reached else "saved"

    async def send_persist_result(bot, chat_id: int, result: str, account_name: str) -> None:
        if result == "saved":
            await bot.send_message(
                chat_id,
                f"تمت إضافة حساب التجميع «{account_name}». سيبدأ العمل خلال ثوانٍ.",
                reply_markup=accounts_menu_keyboard(),
            )
        elif result == "limit_reached":
            await bot.send_message(
                chat_id,
                f"الحد الأقصى هو {MAX_ACTIVE_SOURCE_ACCOUNTS} حسابات نشطة. "
                "أوقف حسابًا أولًا ثم حاول مجددًا.",
                reply_markup=accounts_menu_keyboard(),
            )
        else:
            await bot.send_message(chat_id, "تعذر اعتماد جلسة Telegram. حاول من جديد.")

    async def save_pending_session(
        state: FSMContext,
        client: TelegramClient,
        *,
        account_name: str,
    ) -> None:
        session_string = client.session.save()
        if not session_string:
            raise RuntimeError("Telegram did not produce a pending session")
        await state.update_data(
            source_account_name=account_name,
            pending_session=cipher.encrypt(session_string),
        )

    async def complete_qr_login(
        *,
        telegram_user_id: int,
        bot,
        state: FSMContext,
        client: TelegramClient,
        qr_login,
        account_name: str,
        qr_message_id: int,
    ) -> None:
        preserve_session = False
        try:
            await qr_login.wait(timeout=120)
            result = await persist_authenticated_client(client, account_name=account_name)
            await state.clear()
            await send_persist_result(bot, telegram_user_id, result, account_name)
        except SessionPasswordNeededError:
            preserve_session = True
            await save_pending_session(state, client, account_name=account_name)
            await state.set_state(SourceAccountStates.waiting_for_password)
            await bot.send_message(
                telegram_user_id,
                "الحساب محمي بالتحقق بخطوتين. أرسل كلمة مرور Telegram الآن؛ "
                "سيتم حذف الرسالة فورًا.",
            )
        except TimeoutError:
            await state.clear()
            await bot.send_message(telegram_user_id, "انتهت صلاحية QR. ابدأ الإضافة من جديد.")
        except FloodWaitError as exc:
            await state.clear()
            await bot.send_message(
                telegram_user_id,
                f"Telegram طلب الانتظار {exc.seconds} ثانية قبل المحاولة مجددًا.",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - Telegram authorization boundary
            await state.clear()
            logger.error("source_account_qr_login_failed error_code=%s", type(exc).__name__)
            await bot.send_message(telegram_user_id, "فشل تسجيل الحساب عبر QR. حاول مجددًا.")
        finally:
            await client.disconnect()
            try:
                await bot.delete_message(telegram_user_id, qr_message_id)
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
            if qr_tasks.get(telegram_user_id) is asyncio.current_task():
                qr_tasks.pop(telegram_user_id, None)
            if preserve_session:
                logger.info("source_account_qr_requires_2fa")

    @router.message(Command("accounts"))
    async def accounts_command(message: Message, state: FSMContext) -> None:
        if not await require_manager(message):
            return
        await state.clear()
        await message.answer("إدارة حسابات التجميع:", reply_markup=accounts_menu_keyboard())

    @router.callback_query(F.data == "accounts:menu")
    async def accounts_menu(callback: CallbackQuery, state: FSMContext) -> None:
        if not await require_manager(callback):
            return
        await state.clear()
        await callback.answer()
        await callback.bot.send_message(
            callback.from_user.id,
            "إدارة حسابات التجميع:",
            reply_markup=accounts_menu_keyboard(),
        )

    @router.callback_query(F.data == "accounts:list")
    async def list_accounts(callback: CallbackQuery) -> None:
        if not await require_manager(callback):
            return
        async with session_factory() as session:
            accounts = await SourceAccountRepository(session).list_all()
        await callback.answer()
        await callback.bot.send_message(
            callback.from_user.id,
            format_accounts(accounts),
            reply_markup=accounts_list_keyboard(accounts),
        )

    @router.callback_query(F.data == "accounts:add")
    async def add_account(callback: CallbackQuery, state: FSMContext) -> None:
        if not await require_manager(callback):
            return
        async with session_factory() as session:
            active_count = await SourceAccountRepository(session).count_active()
        if active_count >= MAX_ACTIVE_SOURCE_ACCOUNTS:
            await callback.answer(
                f"الحد الأقصى {MAX_ACTIVE_SOURCE_ACCOUNTS} حسابات نشطة.",
                show_alert=True,
            )
            return
        old_task = qr_tasks.pop(callback.from_user.id, None)
        if old_task is not None:
            old_task.cancel()
        await state.clear()
        await state.set_state(SourceAccountStates.waiting_for_name)
        await callback.answer()
        await callback.bot.send_message(
            callback.from_user.id,
            "اكتب اسمًا مميزًا لحساب التجميع، مثل: حساب التجميع 1",
        )

    @router.message(SourceAccountStates.waiting_for_name, F.text)
    async def receive_account_name(message: Message, state: FSMContext) -> None:
        if not await require_manager(message):
            await state.clear()
            return
        account_name = " ".join((message.text or "").split())
        if not account_name or len(account_name) > 120:
            await message.answer("اسم الحساب مطلوب ويجب ألا يزيد عن 120 حرفًا.")
            return
        await state.update_data(source_account_name=account_name)
        await state.set_state(SourceAccountStates.waiting_for_method)
        await message.answer("اختر طريقة تسجيل حساب Telegram:", reply_markup=login_method_keyboard())

    @router.callback_query(
        SourceAccountStates.waiting_for_method,
        F.data == "accounts:login:phone",
    )
    async def choose_phone_login(callback: CallbackQuery, state: FSMContext) -> None:
        if not await require_manager(callback):
            await state.clear()
            return
        await state.set_state(SourceAccountStates.waiting_for_phone)
        await callback.answer()
        await callback.bot.send_message(
            callback.from_user.id,
            "أرسل رقم الهاتف بصيغة دولية، مثال: +9665XXXXXXXX. "
            "سيتم حذف الرسالة فورًا.",
        )

    @router.message(SourceAccountStates.waiting_for_phone, F.text)
    async def receive_phone(message: Message, state: FSMContext) -> None:
        if not await require_manager(message):
            await state.clear()
            return
        phone = re.sub(r"[\s()-]", "", message.text or "")
        await delete_sensitive_message(message)
        if _PHONE_PATTERN.fullmatch(phone) is None:
            await message.answer("رقم غير صالح. أرسله بصيغة دولية تبدأ بعلامة +.")
            return
        client = TelegramClient(StringSession(), api_id, api_hash)
        try:
            await client.connect()
            sent_code = await client.send_code_request(phone)
            data = await state.get_data()
            account_name = data.get("source_account_name")
            if not isinstance(account_name, str):
                await state.clear()
                await message.answer("انتهت جلسة الإضافة. ابدأ من جديد.")
                return
            await save_pending_session(state, client, account_name=account_name)
            await state.update_data(
                pending_phone=cipher.encrypt(phone),
                pending_phone_code_hash=cipher.encrypt(sent_code.phone_code_hash),
            )
            await state.set_state(SourceAccountStates.waiting_for_code)
            await message.answer(
                "أرسل كود تسجيل الدخول الذي وصلك من Telegram. سيتم حذف الرسالة فورًا."
            )
        except PhoneNumberInvalidError:
            await message.answer("Telegram رفض رقم الهاتف. تأكد من الرقم وحاول مجددًا.")
        except FloodWaitError as exc:
            await state.clear()
            await message.answer(f"يجب الانتظار {exc.seconds} ثانية قبل المحاولة مجددًا.")
        except Exception as exc:  # noqa: BLE001 - Telegram authorization boundary
            await state.clear()
            logger.error("source_account_code_request_failed error_code=%s", type(exc).__name__)
            await message.answer("تعذر إرسال كود Telegram. حاول مجددًا.")
        finally:
            await client.disconnect()

    @router.message(SourceAccountStates.waiting_for_code, F.text)
    async def receive_code(message: Message, state: FSMContext) -> None:
        if not await require_manager(message):
            await state.clear()
            return
        code = re.sub(r"\D", "", message.text or "")
        await delete_sensitive_message(message)
        data = await state.get_data()
        try:
            account_name = data["source_account_name"]
            session_string = cipher.decrypt(data["pending_session"])
            phone = cipher.decrypt(data["pending_phone"])
            phone_code_hash = cipher.decrypt(data["pending_phone_code_hash"])
        except (KeyError, TypeError, ValueError):
            await state.clear()
            await message.answer("انتهت جلسة الإضافة. ابدأ من جديد.")
            return
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
        try:
            await client.connect()
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            result = await persist_authenticated_client(client, account_name=account_name)
            await state.clear()
            await send_persist_result(message.bot, message.from_user.id, result, account_name)
        except SessionPasswordNeededError:
            await save_pending_session(state, client, account_name=account_name)
            await state.set_state(SourceAccountStates.waiting_for_password)
            await message.answer(
                "الحساب محمي بالتحقق بخطوتين. أرسل كلمة مرور Telegram؛ "
                "سيتم حذف الرسالة فورًا."
            )
        except PhoneCodeInvalidError:
            await message.answer("الكود غير صحيح. أرسل الكود الصحيح.")
        except PhoneCodeExpiredError:
            await state.clear()
            await message.answer("انتهت صلاحية الكود. ابدأ الإضافة من جديد.")
        except FloodWaitError as exc:
            await state.clear()
            await message.answer(f"يجب الانتظار {exc.seconds} ثانية قبل المحاولة مجددًا.")
        except Exception as exc:  # noqa: BLE001 - Telegram authorization boundary
            await state.clear()
            logger.error("source_account_sign_in_failed error_code=%s", type(exc).__name__)
            await message.answer("فشل تسجيل الحساب. حاول من جديد.")
        finally:
            await client.disconnect()

    @router.message(SourceAccountStates.waiting_for_password, F.text)
    async def receive_2fa_password(message: Message, state: FSMContext) -> None:
        if not await require_manager(message):
            await state.clear()
            return
        password = message.text or ""
        await delete_sensitive_message(message)
        data = await state.get_data()
        try:
            account_name = data["source_account_name"]
            session_string = cipher.decrypt(data["pending_session"])
        except (KeyError, TypeError, ValueError):
            await state.clear()
            await message.answer("انتهت جلسة الإضافة. ابدأ من جديد.")
            return
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
        try:
            await client.connect()
            await client.sign_in(password=password)
            result = await persist_authenticated_client(client, account_name=account_name)
            await state.clear()
            await send_persist_result(message.bot, message.from_user.id, result, account_name)
        except PasswordHashInvalidError:
            await message.answer("كلمة المرور غير صحيحة. حاول مرة أخرى.")
        except FloodWaitError as exc:
            await state.clear()
            await message.answer(f"يجب الانتظار {exc.seconds} ثانية قبل المحاولة مجددًا.")
        except Exception as exc:  # noqa: BLE001 - Telegram authorization boundary
            await state.clear()
            logger.error("source_account_2fa_failed error_code=%s", type(exc).__name__)
            await message.answer("فشل التحقق بخطوتين. ابدأ الإضافة من جديد.")
        finally:
            await client.disconnect()

    @router.callback_query(
        SourceAccountStates.waiting_for_method,
        F.data == "accounts:login:qr",
    )
    async def choose_qr_login(callback: CallbackQuery, state: FSMContext) -> None:
        if not await require_manager(callback):
            await state.clear()
            return
        data = await state.get_data()
        account_name = data.get("source_account_name")
        if not isinstance(account_name, str):
            await state.clear()
            await callback.answer("انتهت جلسة الإضافة.", show_alert=True)
            return
        old_task = qr_tasks.pop(callback.from_user.id, None)
        if old_task is not None:
            old_task.cancel()
        client = TelegramClient(StringSession(), api_id, api_hash)
        try:
            await client.connect()
            qr_login = await client.qr_login()
            photo = BufferedInputFile(build_qr_png(qr_login.url), filename="telegram-login.png")
            await callback.answer()
            qr_message = await callback.bot.send_photo(
                callback.from_user.id,
                photo,
                caption=(
                    "من Telegram افتح: الإعدادات ← الأجهزة ← ربط جهاز، ثم امسح QR. "
                    "تنتهي صلاحيته خلال دقيقتين."
                ),
            )
            qr_tasks[callback.from_user.id] = asyncio.create_task(
                complete_qr_login(
                    telegram_user_id=callback.from_user.id,
                    bot=callback.bot,
                    state=state,
                    client=client,
                    qr_login=qr_login,
                    account_name=account_name,
                    qr_message_id=qr_message.message_id,
                ),
                name=f"telegram-qr-login-{callback.from_user.id}",
            )
        except Exception as exc:  # noqa: BLE001 - Telegram authorization boundary
            await client.disconnect()
            await state.clear()
            logger.error("source_account_qr_start_failed error_code=%s", type(exc).__name__)
            await callback.answer("تعذر إنشاء QR.", show_alert=True)

    @router.callback_query(F.data.startswith("accounts:enable:"))
    @router.callback_query(F.data.startswith("accounts:disable:"))
    async def toggle_account(callback: CallbackQuery) -> None:
        if not await require_manager(callback):
            return
        parts = (callback.data or "").split(":")
        try:
            account_id = uuid.UUID(parts[-1])
        except (ValueError, IndexError):
            await callback.answer("طلب غير صالح.", show_alert=True)
            return
        active = parts[1] == "enable"
        async with session_factory() as session:
            result = await SourceAccountRepository(session).set_active(
                account_id,
                active=active,
            )
            await session.commit()
            accounts = await SourceAccountRepository(session).list_all()
        if result == "limit_reached":
            await callback.answer(
                f"الحد الأقصى {MAX_ACTIVE_SOURCE_ACCOUNTS} حسابات نشطة.",
                show_alert=True,
            )
            return
        await callback.answer("تم تحديث الحساب." if result == "updated" else "الحساب غير موجود.")
        if callback.message and result == "updated":
            await callback.message.edit_text(
                format_accounts(accounts),
                reply_markup=accounts_list_keyboard(accounts),
            )

    @router.callback_query(F.data == "accounts:cancel")
    async def cancel_account_setup(callback: CallbackQuery, state: FSMContext) -> None:
        task = qr_tasks.pop(callback.from_user.id, None)
        if task is not None:
            task.cancel()
        await state.clear()
        await callback.answer("تم الإلغاء.")
        await callback.bot.send_message(
            callback.from_user.id,
            "تم إلغاء إضافة الحساب.",
            reply_markup=accounts_menu_keyboard(),
        )

    async def shutdown_qr_tasks() -> None:
        tasks = list(qr_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        qr_tasks.clear()

    router.shutdown.register(shutdown_qr_tasks)
    return router
