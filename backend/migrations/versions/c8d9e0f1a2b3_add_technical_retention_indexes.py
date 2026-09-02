"""Добавить индексы для bounded retention технических данных.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
"""

from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_auth_sessions_expires_at",
        "auth_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_sessions_revoked_at",
        "auth_sessions",
        ["revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_telegram_updates_processed_at",
        "telegram_updates",
        ["processed_at"],
        unique=False,
    )
    op.create_index(
        "ix_notification_outbox_status_updated_at",
        "notification_outbox",
        ["status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_access_requests_status_decided_at",
        "access_requests",
        ["status", "decided_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_access_requests_status_decided_at",
        table_name="access_requests",
    )
    op.drop_index(
        "ix_notification_outbox_status_updated_at",
        table_name="notification_outbox",
    )
    op.drop_index(
        "ix_telegram_updates_processed_at",
        table_name="telegram_updates",
    )
    op.drop_index(
        "ix_auth_sessions_revoked_at",
        table_name="auth_sessions",
    )
    op.drop_index(
        "ix_auth_sessions_expires_at",
        table_name="auth_sessions",
    )
