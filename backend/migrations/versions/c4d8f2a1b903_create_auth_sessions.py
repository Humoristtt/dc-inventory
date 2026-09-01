"""Создать серверные auth-сессии.

Revision ID: c4d8f2a1b903
Revises: 7b0e3f6a9c21
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d8f2a1b903"
down_revision: str | Sequence[str] | None = "7b0e3f6a9c21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать таблицу отзывных серверных сессий."""
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32",
            name=op.f("ck_auth_sessions_token_hash_sha256_length"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_auth_sessions_expiry_after_creation"),
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name=op.f("ck_auth_sessions_revoked_after_creation"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint(
            "token_hash",
            name=op.f("uq_auth_sessions_token_hash"),
        ),
    )
    op.create_index(
        "ix_auth_sessions_user_id_expires_at",
        "auth_sessions",
        ["user_id", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    """Удалить таблицу серверных сессий."""
    op.drop_index(
        "ix_auth_sessions_user_id_expires_at",
        table_name="auth_sessions",
    )
    op.drop_table("auth_sessions")
