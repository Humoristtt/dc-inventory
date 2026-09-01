"""Создать Telegram delivery/outbox tables.

Revision ID: e8f1a2b3c4d5
Revises: c4d8f2a1b903
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e8f1a2b3c4d5"
down_revision: str | Sequence[str] | None = "c4d8f2a1b903"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=8),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "method IN ('sendMessage', 'editMessageText', "
            "'editMessageReplyMarkup', 'answerCallbackQuery')",
            name=op.f("ck_notification_outbox_telegram_method"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SENT', 'DEAD')",
            name=op.f("ck_notification_outbox_status"),
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name=op.f("ck_notification_outbox_attempts_non_negative"),
        ),
        sa.CheckConstraint(
            "(claimed_at IS NULL AND claim_token IS NULL) "
            "OR (claimed_at IS NOT NULL AND claim_token IS NOT NULL)",
            name=op.f("ck_notification_outbox_claim_state"),
        ),
        sa.CheckConstraint(
            "(status = 'SENT' AND sent_at IS NOT NULL) "
            "OR (status <> 'SENT' AND sent_at IS NULL)",
            name=op.f("ck_notification_outbox_sent_state"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_outbox")),
        sa.UniqueConstraint(
            "dedupe_key",
            name=op.f("uq_notification_outbox_dedupe_key"),
        ),
    )
    op.create_index(
        "ix_notification_outbox_delivery",
        "notification_outbox",
        ["status", "available_at", "claimed_at"],
        unique=False,
    )

    op.create_table(
        "telegram_updates",
        sa.Column(
            "update_id",
            sa.BigInteger(),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "update_id >= 0",
            name=op.f("ck_telegram_updates_update_id_non_negative"),
        ),
        sa.PrimaryKeyConstraint("update_id", name=op.f("pk_telegram_updates")),
    )

    op.create_table(
        "access_decision_callbacks",
        sa.Column("token", sa.String(length=48), nullable=False),
        sa.Column("access_request_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('APPROVE', 'REJECT')",
            name=op.f("ck_access_decision_callbacks_action"),
        ),
        sa.ForeignKeyConstraint(
            ["access_request_id"],
            ["access_requests.id"],
            name=op.f(
                "fk_access_decision_callbacks_access_request_id_access_requests"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "token",
            name=op.f("pk_access_decision_callbacks"),
        ),
        sa.UniqueConstraint(
            "access_request_id",
            "action",
            name="uq_access_decision_callbacks_request_action",
        ),
    )
    op.create_index(
        "ix_access_decision_callbacks_access_request_id",
        "access_decision_callbacks",
        ["access_request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_access_decision_callbacks_access_request_id",
        table_name="access_decision_callbacks",
    )
    op.drop_table("access_decision_callbacks")
    op.drop_table("telegram_updates")
    op.drop_index(
        "ix_notification_outbox_delivery",
        table_name="notification_outbox",
    )
    op.drop_table("notification_outbox")
