"""remove unused auth session last_seen_at

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: str | Sequence[str] | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("auth_sessions", "last_seen_at")


def downgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
