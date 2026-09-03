"""Allow sendPhoto in Telegram notification outbox.

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-09-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e0f1a2b3c4d5"
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
        "method IN ('sendMessage', 'sendPhoto', 'deleteMessage', "
        "'editMessageText', 'editMessageReplyMarkup', "
        "'answerCallbackQuery')",
    )


def downgrade() -> None:
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
