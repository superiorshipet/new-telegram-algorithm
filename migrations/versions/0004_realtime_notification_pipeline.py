"""Add observations, lead classification, and notification outbox.

Revision ID: 0004_realtime_pipeline
Revises: 0003_default_filters
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_realtime_pipeline"
down_revision: str | None = "0003_default_filters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collected_messages",
        sa.Column("text_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "collected_messages",
        sa.Column("is_lead", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "collected_messages",
        sa.Column(
            "matched_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "collected_messages",
        sa.Column("match_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        op.f("ix_collected_messages_is_lead"),
        "collected_messages",
        ["is_lead"],
    )
    op.create_index(
        "ix_collected_messages_sender_fingerprint",
        "collected_messages",
        ["sender_telegram_id", "text_fingerprint"],
    )

    op.create_table(
        "message_observations",
        sa.Column("collected_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["collected_message_id"],
            ["collected_messages.id"],
            name=op.f("fk_message_observations_collected_message_id_collected_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_account_id"],
            ["source_accounts.id"],
            name=op.f("fk_message_observations_source_account_id_source_accounts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_observations")),
        sa.UniqueConstraint(
            "collected_message_id",
            "source_account_id",
            name="uq_message_observations_message_source",
        ),
    )
    op.create_index(
        op.f("ix_message_observations_collected_message_id"),
        "message_observations",
        ["collected_message_id"],
    )
    op.create_index(
        op.f("ix_message_observations_source_account_id"),
        "message_observations",
        ["source_account_id"],
    )

    op.create_table(
        "notification_outbox",
        sa.Column("collected_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
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
            ["collected_message_id"],
            ["collected_messages.id"],
            name=op.f("fk_notification_outbox_collected_message_id_collected_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_outbox")),
        sa.UniqueConstraint(
            "collected_message_id",
            name=op.f("uq_notification_outbox_collected_message_id"),
        ),
    )
    op.create_index(
        "ix_notification_outbox_status_available",
        "notification_outbox",
        ["status", "available_at"],
    )

    op.execute(
        """
        CREATE FUNCTION notify_lead_outbox() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('lead_notifications', NEW.id::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER notification_outbox_inserted
        AFTER INSERT ON notification_outbox
        FOR EACH ROW EXECUTE FUNCTION notify_lead_outbox()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS notification_outbox_inserted ON notification_outbox")
    op.execute("DROP FUNCTION IF EXISTS notify_lead_outbox()")
    op.drop_table("notification_outbox")
    op.drop_table("message_observations")
    op.drop_index(
        "ix_collected_messages_sender_fingerprint",
        table_name="collected_messages",
    )
    op.drop_index(op.f("ix_collected_messages_is_lead"), table_name="collected_messages")
    op.drop_column("collected_messages", "match_reason")
    op.drop_column("collected_messages", "matched_keywords")
    op.drop_column("collected_messages", "is_lead")
    op.drop_column("collected_messages", "text_fingerprint")
