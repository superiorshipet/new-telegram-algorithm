"""Version default filter seeding.

Revision ID: 0005_filter_versions
Revises: 0004_realtime_pipeline
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_filter_versions"
down_revision: str | None = "0004_realtime_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bot_users",
        sa.Column(
            "default_filter_version",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE bot_users
        SET default_filter_version = CASE
            WHEN default_filters_seeded THEN 1
            ELSE 0
        END
        """
    )


def downgrade() -> None:
    op.drop_column("bot_users", "default_filter_version")
