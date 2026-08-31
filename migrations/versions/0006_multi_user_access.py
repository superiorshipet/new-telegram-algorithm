"""Add owner-managed access grants and per-user notification delivery.

Revision ID: 0006_multi_user_access
Revises: 0005_filter_versions
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_multi_user_access"
down_revision: str | None = "0005_filter_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_access_grants",
        sa.Column("subject_type", sa.String(length=20), nullable=False),
        sa.Column("subject_value", sa.String(length=255), nullable=False),
        sa.Column("granted_by_telegram_user_id", sa.BigInteger(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bot_access_grants")),
        sa.UniqueConstraint(
            "subject_type", "subject_value", name="uq_bot_access_grants_subject"
        ),
    )
    op.create_index(
        op.f("ix_bot_access_grants_is_active"),
        "bot_access_grants",
        ["is_active"],
    )

    op.add_column(
        "notification_outbox",
        sa.Column("bot_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("notification_outbox", sa.Column("is_lead", sa.Boolean(), nullable=True))
    op.add_column(
        "notification_outbox",
        sa.Column(
            "matched_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("notification_outbox", sa.Column("match_reason", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE notification_outbox
        SET bot_user_id = (
            SELECT id FROM bot_users ORDER BY created_at, id LIMIT 1
        )
        """
    )
    op.execute("DELETE FROM notification_outbox WHERE bot_user_id IS NULL")
    op.alter_column("notification_outbox", "bot_user_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_notification_outbox_bot_user_id_bot_users"),
        "notification_outbox",
        "bot_users",
        ["bot_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_notification_outbox_bot_user_id"),
        "notification_outbox",
        ["bot_user_id"],
    )
    op.drop_constraint(
        op.f("uq_notification_outbox_collected_message_id"),
        "notification_outbox",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_notification_outbox_message_user",
        "notification_outbox",
        ["collected_message_id", "bot_user_id"],
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM notification_outbox first_row
        USING notification_outbox duplicate_row
        WHERE first_row.collected_message_id = duplicate_row.collected_message_id
          AND first_row.id::text > duplicate_row.id::text
        """
    )
    op.drop_constraint(
        "uq_notification_outbox_message_user", "notification_outbox", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_notification_outbox_collected_message_id"),
        "notification_outbox",
        ["collected_message_id"],
    )
    op.drop_index(op.f("ix_notification_outbox_bot_user_id"), table_name="notification_outbox")
    op.drop_constraint(
        op.f("fk_notification_outbox_bot_user_id_bot_users"),
        "notification_outbox",
        type_="foreignkey",
    )
    op.drop_column("notification_outbox", "match_reason")
    op.drop_column("notification_outbox", "matched_keywords")
    op.drop_column("notification_outbox", "is_lead")
    op.drop_column("notification_outbox", "bot_user_id")
    op.drop_index(op.f("ix_bot_access_grants_is_active"), table_name="bot_access_grants")
    op.drop_table("bot_access_grants")
