"""Track one-time default filter seeding.

Revision ID: 0003_default_filters
Revises: 0002_bot_features
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_default_filters"
down_revision: str | None = "0002_bot_features"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bot_users",
        sa.Column(
            "default_filters_seeded",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("bot_users", "default_filters_seeded")
