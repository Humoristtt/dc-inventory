"""Add Telegram start welcome state and deleteMessage delivery.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e0f1a2b3c4d5"
down_revision: str | Sequence[str] | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_notification_outbox_telegram_method"),
        "notification_outbox",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_notification_outbox_telegram_method"),
        "notification_outbox",
        "method IN ('sendMessage', 'deleteMessage', 'editMessageText', "
        "'editMessageReplyMarkup', 'answerCallbackQuery')",
    )

    op.create_table(
        "telegram_chat_states",
        sa.Column("chat_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column(
            "latest_start_update_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "last_welcome_message_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "last_welcome_sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
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
        sa.CheckConstraint(
            "latest_start_update_id >= 0",
            name=op.f(
                "ck_telegram_chat_states_latest_start_update_id_non_negative"
            ),
        ),
        sa.CheckConstraint(
            "(last_welcome_message_id IS NULL "
            "AND last_welcome_sent_at IS NULL) "
            "OR (last_welcome_message_id IS NOT NULL "
            "AND last_welcome_sent_at IS NOT NULL)",
            name=op.f("ck_telegram_chat_states_last_welcome_pair"),
        ),
        sa.PrimaryKeyConstraint(
            "chat_id",
            name=op.f("pk_telegram_chat_states"),
        ),
    )


def downgrade() -> None:
    op.drop_table("telegram_chat_states")

    op.drop_constraint(
        op.f("ck_notification_outbox_telegram_method"),
        "notification_outbox",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_notification_outbox_telegram_method"),
        "notification_outbox",
        "method IN ('sendMessage', 'editMessageText', "
        "'editMessageReplyMarkup', 'answerCallbackQuery')",
    )
