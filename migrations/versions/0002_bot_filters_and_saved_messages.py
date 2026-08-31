"""Add bot-user filters and saved messages.

Revision ID: 0002_bot_features
Revises: 0001_initial
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_bot_features"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_user_keywords",
        sa.Column("bot_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword", sa.String(length=100), nullable=False),
        sa.Column("normalized_keyword", sa.String(length=100), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["bot_user_id"],
            ["bot_users.id"],
            name=op.f("fk_bot_user_keywords_bot_user_id_bot_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bot_user_keywords")),
        sa.UniqueConstraint(
            "bot_user_id",
            "normalized_keyword",
            name="uq_bot_user_keywords_user_normalized",
        ),
    )
    op.create_index(
        op.f("ix_bot_user_keywords_bot_user_id"),
        "bot_user_keywords",
        ["bot_user_id"],
    )

    op.create_table(
        "saved_messages",
        sa.Column("bot_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collected_message_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["bot_user_id"],
            ["bot_users.id"],
            name=op.f("fk_saved_messages_bot_user_id_bot_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["collected_message_id"],
            ["collected_messages.id"],
            name=op.f("fk_saved_messages_collected_message_id_collected_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_messages")),
        sa.UniqueConstraint(
            "bot_user_id",
            "collected_message_id",
            name="uq_saved_messages_user_message",
        ),
    )
    op.create_index(
        op.f("ix_saved_messages_bot_user_id"),
        "saved_messages",
        ["bot_user_id"],
    )
    op.create_index(
        op.f("ix_saved_messages_collected_message_id"),
        "saved_messages",
        ["collected_message_id"],
    )


def downgrade() -> None:
    op.drop_table("saved_messages")
    op.drop_table("bot_user_keywords")
