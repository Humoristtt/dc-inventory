"""add admin user search indexes

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-12 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INDEXES = (
    (
        "ix_telegram_identities_username_trgm",
        "username",
    ),
    (
        "ix_telegram_identities_first_name_trgm",
        "first_name",
    ),
    (
        "ix_telegram_identities_last_name_trgm",
        "last_name",
    ),
)


def upgrade() -> None:
    for name, column in INDEXES:
        op.create_index(
            name,
            "telegram_identities",
            [column],
            unique=False,
            postgresql_using="gin",
            postgresql_ops={
                column: "gin_trgm_ops",
            },
        )


def downgrade() -> None:
    for name, _ in reversed(INDEXES):
        op.drop_index(
            name,
            table_name="telegram_identities",
        )
