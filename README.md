# Telegram Leads System

A Python 3.12 monorepo with two independently deployable Railway workers:

- `collector-worker` connects authorized Telegram user accounts in read-only mode,
  listens for new group messages, and persists them through a bounded queue.
- `bot-worker` registers private-chat users, manages their filters, and provides matching
  and saved opportunities.
- PostgreSQL stores shared source accounts, groups, messages, and bot users.

Automatic push delivery is intentionally outside this milestone; users can already browse
matching messages through `/latest` and keep selected results through `/saved`.

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

2. Copy the example file and fill the local values. `.env` is ignored by Git and loaded
   automatically for local development; real process/Railway variables take precedence:

   ```bash
   cp .env.example .env
   chmod 600 .env
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
| bot-worker | `python -m app.bot` | `DATABASE_URL`, `BOT_TOKEN`, `BOT_OWNER_TELEGRAM_ID` |
| collector-worker | `python -m app.collector` | `DATABASE_URL`, `MASTER_ENCRYPTION_KEY` |

Use Railway's private `DATABASE_URL` for both workers. Run `alembic upgrade head` as a
one-off deployment command before starting the workers. Do not run migrations concurrently
from both workers.

The bot username is presentation metadata managed by BotFather; application code only
requires `BOT_TOKEN`. At startup the worker synchronizes the supported BotFather command
menu automatically. Open the bot in a private chat and send `/start` to register.

## Bot commands

- `/start` registers a new user or reactivates notifications for an existing user.
- `/filters` opens an interactive menu. Press `Add`, send words or phrases separated by
  new lines, English commas, or Arabic commas, review the preview, then press `Add` again
  to save them.
- `/filters add Python, .NET, تصميم مواقع` adds unique keywords or phrases without a
  per-user count limit.
- `/filters remove Python` removes one or more comma-separated filters.
- `/filters clear` removes every filter.
- `/latest` displays the five newest messages matching any configured filter. With no
  filters it displays the five newest collected messages.
- `/saved` displays the ten most recently saved messages.
- `/status` displays registration, notification, filter, and saved-message status.
- `/stop` pauses future push notifications; `/start` reactivates them.

Messages returned by `/latest` contain a save button and, when available, a link to the
original Telegram message. Saved results contain a remove button.

On the first `/start` after the default-filter migration, the bot adds the built-in Arabic
lead keywords once. Users can remove or replace them; removed defaults are not recreated
on later `/start` commands.

## Realtime detection and deduplication

Collectors use Telegram `NewMessage` events; they never scan every group on a timer. Each
source account runs concurrently and event handlers place work into a bounded queue.

- The unique Telegram identity is `(group, message_id)`. If two source accounts see that
  exact message, one message row and one notification are created while both observations
  are recorded in `message_observations`.
- If the same sender ID posts the same request in another group, the different group makes
  it a separate saved message and separate notification. The alert shows how many distinct
  groups contain that sender/text fingerprint.
- The sender's immutable Telegram user ID is the primary identity. Username and display
  name are retained only as contact/display snapshots.
- Every new message creates a durable outbox task. PostgreSQL `LISTEN/NOTIFY` wakes the bot
  immediately, while a one-second recovery poll ensures pending work is still delivered
  after restarts or listener interruption.
- Classification requires both a configured keyword and request intent/context. The score,
  matched keywords, and reason are stored on the message for auditability.

## Production security checklist

- Set `BOT_OWNER_TELEGRAM_ID` to the immutable ID of the only authorized viewer. Commands,
  callbacks, and realtime notifications are restricted to this ID.
- Rotate every credential that has appeared in chat or screenshots before deployment.
- Keep Telegram API credentials, session strings, bot tokens, phone numbers, and database
  URLs out of Git. Source-account credentials and StringSessions are encrypted at rest with
  `MASTER_ENCRYPTION_KEY`.
- Use Railway's private database URL between deployed services. For remote administration,
  require TLS and restrict database/network access to authorized operators.
- Enable encrypted provider-managed PostgreSQL backups, define retention, and perform a
  periodic restore test. A backup is not considered valid until restoration is verified.
- Grant the runtime database role only the permissions it needs. Use a separate privileged
  role for migrations and backup administration when moving beyond the MVP.
- Logs contain identifiers, status, latency, and error class only; they do not contain
  message bodies, sessions, tokens, API hashes, phone numbers, or database URLs.

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
