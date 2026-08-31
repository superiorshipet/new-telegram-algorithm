"""Create the initial Telegram leads schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_users",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bot_users")),
        sa.UniqueConstraint("telegram_chat_id", name=op.f("uq_bot_users_telegram_chat_id")),
        sa.UniqueConstraint("telegram_user_id", name=op.f("uq_bot_users_telegram_user_id")),
    )
    op.create_index(op.f("ix_bot_users_is_active"), "bot_users", ["is_active"])

    op.create_table(
        "source_accounts",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone_number_masked", sa.String(length=40), nullable=True),
        sa.Column("session_string_encrypted", sa.Text(), nullable=False),
        sa.Column("api_id_encrypted", sa.Text(), nullable=False),
        sa.Column("api_hash_encrypted", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "status", sa.String(length=30), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("flood_wait_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_accounts")),
        sa.UniqueConstraint("name", name=op.f("uq_source_accounts_name")),
    )
    op.create_index(op.f("ix_source_accounts_is_active"), "source_accounts", ["is_active"])

    op.create_table(
        "telegram_groups",
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_groups")),
        sa.UniqueConstraint("telegram_chat_id", name=op.f("uq_telegram_groups_telegram_chat_id")),
    )
    op.create_index(op.f("ix_telegram_groups_is_active"), "telegram_groups", ["is_active"])

    op.create_table(
        "collected_messages",
        sa.Column("telegram_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("sender_name", sa.String(length=255), nullable=True),
        sa.Column("sender_username", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("original_message_link", sa.Text(), nullable=True),
        sa.Column("message_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("preliminary_score", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_account_id"],
            ["source_accounts.id"],
            name=op.f("fk_collected_messages_source_account_id_source_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["telegram_group_id"],
            ["telegram_groups.id"],
            name=op.f("fk_collected_messages_telegram_group_id_telegram_groups"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collected_messages")),
        sa.UniqueConstraint(
            "telegram_group_id",
            "telegram_message_id",
            name="uq_collected_messages_group_message",
        ),
    )
    op.create_index("ix_collected_messages_content_hash", "collected_messages", ["content_hash"])
    op.create_index("ix_collected_messages_message_date", "collected_messages", ["message_date"])
    op.create_index(
        "ix_collected_messages_source_account_id", "collected_messages", ["source_account_id"]
    )


def downgrade() -> None:
    op.drop_table("collected_messages")
    op.drop_table("telegram_groups")
    op.drop_table("source_accounts")
    op.drop_table("bot_users")
