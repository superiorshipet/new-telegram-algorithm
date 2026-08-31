# Telegram Leads System

A Python 3.12 monorepo with two independently deployable Railway workers:

- `collector-worker` connects authorized Telegram user accounts in read-only mode,
  listens for new group messages, and persists them through a bounded queue.
- `bot-worker` registers private-chat users by immutable Telegram user/chat IDs.
- PostgreSQL stores shared source accounts, groups, messages, and bot users.

Notification delivery and advanced user filters are intentionally outside this first
milestone.

## Security model

No credentials belong in the repository. Runtime configuration is read from environment
variables only. Source-account API credentials and Telethon StringSessions are encrypted
before database storage using a Fernet `MASTER_ENCRYPTION_KEY`. Logs never include bot
tokens, session strings, API hashes, phone numbers, database URLs, or message bodies.

Any bot token or database URL pasted into chat or another shared location must be rotated
before deployment.

## Local setup

1. Create and activate a virtual environment:

   ```bash
   python3.12 -m venv .venv
   . .venv/bin/activate
   pip install -e '.[dev]'
   ```

2. Export variables locally. `.env` is ignored, but the application deliberately does
   not auto-load it:

   ```bash
   export DATABASE_URL='postgresql://USER:PASSWORD@HOST:PORT/DATABASE'
   export BOT_TOKEN='ROTATED_BOT_TOKEN'
   export MASTER_ENCRYPTION_KEY='FERNET_KEY'
   ```

   Generate the encryption key once and keep the same value in the collector and session
   generation environment:

   ```bash
   python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
   ```

3. Apply the schema:

   ```bash
   alembic upgrade head
   ```

4. Run either worker:

   ```bash
   python -m app.bot
   python -m app.collector
   ```

## Add a Telegram source account

Obtain `TG_API_ID` and `TG_API_HASH` from Telegram's official API development page. In a
trusted local shell, export those values plus `TG_PHONE`, `SOURCE_ACCOUNT_NAME`,
`DATABASE_URL`, and `MASTER_ENCRYPTION_KEY`, then run:

```bash
python -m scripts.generate_session
```

Telethon prompts interactively for the login code and optional two-factor password. The
script writes the resulting StringSession and API credentials directly to PostgreSQL in
encrypted form; it never prints the StringSession. Remove the temporary `TG_*` variables
from the shell afterward.

## Railway deployment

Create PostgreSQL plus two services from this same repository. Override the Docker start
command per service:

| Service | Start command | Required variables |
| --- | --- | --- |
| bot-worker | `python -m app.bot` | `DATABASE_URL`, `BOT_TOKEN` |
| collector-worker | `python -m app.collector` | `DATABASE_URL`, `MASTER_ENCRYPTION_KEY` |

Use Railway's private `DATABASE_URL` for both workers. Run `alembic upgrade head` as a
one-off deployment command before starting the workers. Do not run migrations concurrently
from both workers.

The bot username is presentation metadata managed by BotFather; application code only
requires `BOT_TOKEN`. Open the bot in a private chat and send `/start` to register.

## Deduplication and processing

Each collected message has a SHA-256 fingerprint over its Telegram chat ID, message ID,
and normalized content. The authoritative deduplication mechanism is PostgreSQL's unique
constraint on `(telegram_group_id, telegram_message_id)`, inserted with
`ON CONFLICT DO NOTHING`. This remains atomic when multiple source accounts observe the
same message simultaneously.

Arabic normalization removes diacritics and tatweel, normalizes common Alef/Ya variants,
case-folds Latin text, and collapses whitespace. Original text remains unchanged in its
own column.

## Tests

Tests do not connect to Telegram or PostgreSQL and do not require real credentials:

```bash
pytest
```
