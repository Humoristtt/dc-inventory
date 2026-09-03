from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

START_WELCOME_DEDUPE_PREFIX = "telegram-start-welcome:"


class TelegramUpdate(Base):
    __tablename__ = "telegram_updates"
    __table_args__ = (
        CheckConstraint("update_id >= 0", name="update_id_non_negative"),
        Index(
            "ix_telegram_updates_processed_at",
            "processed_at",
        ),
    )

    update_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelegramChatState(Base):
    __tablename__ = "telegram_chat_states"
    __table_args__ = (
        CheckConstraint(
            "latest_start_update_id >= 0",
            name="latest_start_update_id_non_negative",
        ),
        CheckConstraint(
            "(last_welcome_message_id IS NULL "
            "AND last_welcome_sent_at IS NULL) "
            "OR (last_welcome_message_id IS NOT NULL "
            "AND last_welcome_sent_at IS NOT NULL)",
            name="last_welcome_pair",
        ),
    )

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
    )
    latest_start_update_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    last_welcome_message_id: Mapped[int | None] = mapped_column(BigInteger)
    last_welcome_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
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


class AccessDecisionCallback(Base):
    __tablename__ = "access_decision_callbacks"
    __table_args__ = (
        CheckConstraint(
            "action IN ('APPROVE', 'REJECT')",
            name="action",
        ),
        UniqueConstraint(
            "access_request_id",
            "action",
            name="uq_access_decision_callbacks_request_action",
        ),
        Index(
            "ix_access_decision_callbacks_access_request_id",
            "access_request_id",
        ),
    )

    token: Mapped[str] = mapped_column(String(48), primary_key=True)
    access_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
