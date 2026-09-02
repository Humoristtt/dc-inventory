from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        CheckConstraint(
            "method IN ('sendMessage', 'editMessageText', "
            "'editMessageReplyMarkup', 'answerCallbackQuery')",
            name="telegram_method",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'SENT', 'DEAD')",
            name="status",
        ),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint(
            "(claimed_at IS NULL AND claim_token IS NULL) "
            "OR (claimed_at IS NOT NULL AND claim_token IS NOT NULL)",
            name="claim_state",
        ),
        CheckConstraint(
            "(status = 'SENT' AND sent_at IS NOT NULL) "
            "OR (status <> 'SENT' AND sent_at IS NULL)",
            name="sent_state",
        ),
        Index(
            "ix_notification_outbox_delivery",
            "status",
            "available_at",
            "claimed_at",
        ),
        Index(
            "ix_notification_outbox_status_updated_at",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
