from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.identity.enums import (
    AccessRequestStatus,
    UserAccessStatus,
    UserRole,
)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('USER', 'ADMIN')",
            name="user_role",
        ),
        CheckConstraint(
            "access_status IN ('PENDING', 'APPROVED', 'REJECTED', 'BLOCKED')",
            name="user_access_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        nullable=False,
        default=UserRole.USER,
        server_default=UserRole.USER.value,
    )
    access_status: Mapped[UserAccessStatus] = mapped_column(
        Enum(
            UserAccessStatus,
            name="user_access_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        nullable=False,
        default=UserAccessStatus.PENDING,
        server_default=UserAccessStatus.PENDING.value,
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
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
    )

    telegram_identity: Mapped[TelegramIdentity | None] = relationship(
        back_populates="user",
        uselist=False,
    )
    access_requests: Mapped[list[AccessRequest]] = relationship(
        back_populates="user",
        foreign_keys="AccessRequest.user_id",
    )
    approved_by: Mapped[User | None] = relationship(
        remote_side=[id],
        foreign_keys=[approved_by_user_id],
    )


class TelegramIdentity(Base):
    __tablename__ = "telegram_identities"
    __table_args__ = (
        CheckConstraint(
            "telegram_user_id > 0",
            name="telegram_user_id_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
    )
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str | None] = mapped_column(String(35))
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
    last_auth_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="telegram_identity")


class AccessRequest(Base):
    __tablename__ = "access_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="access_request_status",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND decided_at IS NULL "
            "AND decided_by_user_id IS NULL) "
            "OR (status IN ('APPROVED', 'REJECTED') "
            "AND decided_at IS NOT NULL "
            "AND decided_by_user_id IS NOT NULL)",
            name="decision_state",
        ),
        Index(
            "ux_access_requests_user_pending",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "ix_access_requests_status_requested_at",
            "status",
            "requested_at",
        ),
        Index(
            "ix_access_requests_status_decided_at",
            "status",
            "decided_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[AccessRequestStatus] = mapped_column(
        Enum(
            AccessRequestStatus,
            name="access_request_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
        ),
        nullable=False,
        default=AccessRequestStatus.PENDING,
        server_default=AccessRequestStatus.PENDING.value,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    decision_note: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(
        back_populates="access_requests",
        foreign_keys=[user_id],
    )
    decided_by: Mapped[User | None] = relationship(
        foreign_keys=[decided_by_user_id],
    )
