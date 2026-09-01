"""Add indexes to support periodic outbox and message retention cleanup.

Revision ID: 0008_outbox_retention
Revises: 0007_access_admin_role
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_outbox_retention"
down_revision: str | None = "0007_access_admin_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Index used by the periodic purge query:
    #   DELETE FROM notification_outbox
    #   WHERE status IN ('sent','skipped','failed') AND updated_at < now() - interval
    op.create_index(
        "ix_notification_outbox_status_updated_at",
        "notification_outbox",
        ["status", "updated_at"],
    )

    # Index to speed up retention cleanup on collected_messages by ingest time.
    op.create_index(
        "ix_collected_messages_collected_at",
        "collected_messages",
        ["collected_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_collected_messages_collected_at", table_name="collected_messages")
    op.drop_index("ix_notification_outbox_status_updated_at", table_name="notification_outbox")
