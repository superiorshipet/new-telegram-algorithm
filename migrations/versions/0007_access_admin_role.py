"""Add delegated access administrator role.

Revision ID: 0007_access_admin_role
Revises: 0006_multi_user_access
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_access_admin_role"
down_revision: str | None = "0006_multi_user_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bot_users",
        sa.Column(
            "is_access_admin",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_bot_users_is_access_admin"),
        "bot_users",
        ["is_access_admin"],
    )
    op.add_column(
        "bot_access_grants",
        sa.Column(
            "is_access_admin",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    op.execute(
        """
        UPDATE bot_access_grants
        SET is_access_admin = true
        WHERE subject_type = 'username'
          AND lower(subject_value) = 'm02men1'
        """
    )
    op.execute(
        """
        UPDATE bot_users
        SET is_access_admin = true
        WHERE lower(coalesce(username, '')) = 'm02men1'
        """
    )
    op.execute(
        """
        UPDATE bot_access_grants access_grant
        SET is_access_admin = true
        FROM bot_users bot_user
        WHERE lower(coalesce(bot_user.username, '')) = 'm02men1'
          AND access_grant.subject_type = 'telegram_id'
          AND access_grant.subject_value = bot_user.telegram_user_id::text
        """
    )


def downgrade() -> None:
    op.drop_column("bot_access_grants", "is_access_admin")
    op.drop_index(op.f("ix_bot_users_is_access_admin"), table_name="bot_users")
    op.drop_column("bot_users", "is_access_admin")
