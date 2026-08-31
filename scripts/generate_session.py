from __future__ import annotations

import asyncio
from argparse import ArgumentParser

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from telethon import TelegramClient
from telethon.sessions import StringSession

from app.common.config import get_settings
from app.common.crypto import SecretCipher
from app.database.models import SourceAccount
from app.database.session import Database


def mask_phone(phone: str) -> str:
    if len(phone) <= 4:
        return "*" * len(phone)
    return f"{'*' * (len(phone) - 4)}{phone[-4:]}"


async def run() -> None:
    parser = ArgumentParser(description="Authorize and securely store one Telegram source account.")
    parser.add_argument(
        "--name",
        help="Stable display name such as 'الحساب 1'.",
    )
    arguments = parser.parse_args()

    settings = get_settings()
    encryption_key = settings.require_encryption_key()
    api_id, api_hash = settings.require_telegram_api_values()
    configured_phone = settings.tg_phone.get_secret_value() if settings.tg_phone else ""
    phone = (
        configured_phone.strip() or input("Telegram phone number including country code: ").strip()
    )
    account_name = (
        arguments.name
        or (settings.source_account_name or "").strip()
        or input("Source account display name: ").strip()
    )
    if not phone:
        raise RuntimeError("Telegram phone number is required")
    if not account_name:
        raise RuntimeError("Source account display name is required")
    api_id_text = str(api_id)

    client = TelegramClient(StringSession(), api_id, api_hash)
    try:
        await client.start(phone=phone)
        session_string = client.session.save()
        if not session_string:
            raise RuntimeError("Telegram did not produce a StringSession")
    finally:
        await client.disconnect()

    cipher = SecretCipher(encryption_key)
    database = Database(settings)
    try:
        async with database.session_factory() as session:
            statement = insert(SourceAccount).values(
                name=account_name,
                phone_number_masked=mask_phone(phone),
                session_string_encrypted=cipher.encrypt(session_string),
                api_id_encrypted=cipher.encrypt(api_id_text),
                api_hash_encrypted=cipher.encrypt(api_hash),
                is_active=True,
                status="pending",
            )
            statement = statement.on_conflict_do_update(
                index_elements=[SourceAccount.name],
                set_={
                    "phone_number_masked": statement.excluded.phone_number_masked,
                    "session_string_encrypted": statement.excluded.session_string_encrypted,
                    "api_id_encrypted": statement.excluded.api_id_encrypted,
                    "api_hash_encrypted": statement.excluded.api_hash_encrypted,
                    "is_active": True,
                    "status": "pending",
                    "updated_at": func.now(),
                },
            )
            await session.execute(statement)
            await session.commit()
    finally:
        await database.dispose()

    print(f"Source account {account_name!r} was stored with encrypted credentials.")


if __name__ == "__main__":
    asyncio.run(run())
