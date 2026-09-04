"""Add delegated-admin support data, a new request phrase, and hot-path indexes.

Revision ID: 0009_admin_filters_perf
Revises: 0008_outbox_retention
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_admin_filters_perf"
down_revision: str | None = "0008_outbox_retention"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Seed the new phrase for every existing bot user. The unique constraint keeps
    # this idempotent for users who already added it manually.
    op.execute(
        """
        INSERT INTO bot_user_keywords (
            id,
            bot_user_id,
            keyword,
            normalized_keyword,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            bot_user.id,
            'من يسوي',
            'من يسوي',
            now(),
            now()
        FROM bot_users bot_user
        ON CONFLICT ON CONSTRAINT uq_bot_user_keywords_user_normalized DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE bot_users
        SET default_filters_seeded = true,
            default_filter_version = GREATEST(default_filter_version, 3),
            updated_at = now()
        """
    )

    # Matches the dispatcher claim predicate and ordering while keeping the
    # index small by indexing only actionable rows.
    op.create_index(
        "ix_notification_outbox_pending_dispatch",
        "notification_outbox",
        [sa.text("available_at"), sa.text("created_at")],
        postgresql_where=sa.text("status = 'pending' AND attempts < 10"),
    )

    # Latest opportunities read only lead rows ordered newest-first.
    op.create_index(
        "ix_collected_messages_lead_message_date",
        "collected_messages",
        [sa.text("message_date DESC")],
        postgresql_where=sa.text("is_lead = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collected_messages_lead_message_date",
        table_name="collected_messages",
    )
    op.drop_index(
        "ix_notification_outbox_pending_dispatch",
        table_name="notification_outbox",
    )
    # Preserve user-owned filters and data. Downgrading code version must not
    # silently delete a phrase that a user may now rely on.
