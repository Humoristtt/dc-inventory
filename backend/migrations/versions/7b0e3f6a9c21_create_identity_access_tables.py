"""Создать базовую модель identity и запросов доступа.

Revision ID: 7b0e3f6a9c21
Revises: 48c2f07f01a0
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b0e3f6a9c21"
down_revision: str | Sequence[str] | None = "48c2f07f01a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создать пользователей, Telegram identity и access requests."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.String(length=5),
            server_default=sa.text("'USER'"),
            nullable=False,
        ),
        sa.Column(
            "access_status",
            sa.String(length=8),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "role IN ('USER', 'ADMIN')",
            name=op.f("ck_users_user_role"),
        ),
        sa.CheckConstraint(
            "access_status IN ('PENDING', 'APPROVED', 'REJECTED', 'BLOCKED')",
            name=op.f("ck_users_user_access_status"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            name=op.f("fk_users_approved_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )

    op.create_table(
        "telegram_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=False),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("language_code", sa.String(length=35), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_auth_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "telegram_user_id > 0",
            name=op.f("ck_telegram_identities_telegram_user_id_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_telegram_identities_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telegram_identities")),
        sa.UniqueConstraint(
            "telegram_user_id",
            name=op.f("uq_telegram_identities_telegram_user_id"),
        ),
        sa.UniqueConstraint(
            "user_id",
            name=op.f("uq_telegram_identities_user_id"),
        ),
    )

    op.create_table(
        "access_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=8),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name=op.f("ck_access_requests_access_request_status"),
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND decided_at IS NULL "
            "AND decided_by_user_id IS NULL) "
            "OR (status IN ('APPROVED', 'REJECTED') "
            "AND decided_at IS NOT NULL "
            "AND decided_by_user_id IS NOT NULL)",
            name=op.f("ck_access_requests_decision_state"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name=op.f("fk_access_requests_decided_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_access_requests_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_requests")),
    )
    op.create_index(
        op.f("ix_access_requests_user_id"),
        "access_requests",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_access_requests_status_requested_at",
        "access_requests",
        ["status", "requested_at"],
        unique=False,
    )
    op.create_index(
        "ux_access_requests_user_pending",
        "access_requests",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    """Удалить базовую модель identity и запросов доступа."""
    op.drop_index(
        "ux_access_requests_user_pending",
        table_name="access_requests",
    )
    op.drop_index(
        "ix_access_requests_status_requested_at",
        table_name="access_requests",
    )
    op.drop_index(
        op.f("ix_access_requests_user_id"),
        table_name="access_requests",
    )
    op.drop_table("access_requests")
    op.drop_table("telegram_identities")
    op.drop_table("users")
