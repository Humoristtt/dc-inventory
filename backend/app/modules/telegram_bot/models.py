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


class TelegramUpdate(Base):
    __tablename__ = "telegram_updates"
    __table_args__ = (
        CheckConstraint("update_id >= 0", name="update_id_non_negative"),
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
