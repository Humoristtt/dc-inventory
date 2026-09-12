from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.procurement.enums import (
    ProcurementEventType,
    ProcurementLineType,
    ProcurementStatus,
)


class ProcurementRequest(Base):
    __tablename__ = "procurement_requests"
    __table_args__ = (
        CheckConstraint("btrim(request_number) <> ''", name="request_number_not_blank"),
        CheckConstraint(
            "status IN ('AGREEMENT_PENDING_MANAGER', "
            "'AGREEMENT_REVISION_REQUIRED', 'PURCHASING', "
            "'AWAITING_ACCEPTANCE', 'COMPLETED')",
            name="status",
        ),
        CheckConstraint("state_version >= 1", name="state_version_positive"),
        CheckConstraint(
            "btrim(creation_client_request_id) <> ''", name="creation_client_request_id_not_blank"
        ),
        CheckConstraint("length(request_fingerprint) = 64", name="request_fingerprint_length"),
        UniqueConstraint(
            "initiator_user_id",
            "creation_client_request_id",
            name="uq_procurement_requests_initiator_client_request",
        ),
        CheckConstraint(
            "(status = 'COMPLETED' AND final_movement_id IS NOT NULL "
            "AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED' AND final_movement_id IS NULL "
            "AND completed_at IS NULL)",
            name="completion_state",
        ),
        Index("ix_procurement_requests_status_created", "status", "created_at"),
        Index("ix_procurement_requests_initiator_created", "initiator_user_id", "created_at"),
        Index(
            "ix_procurement_requests_manager_status_created",
            "assigned_manager_user_id",
            "status",
            "created_at",
        ),
        Index("ix_procurement_requests_created_at_id", "created_at", "id"),
        Index(
            "ix_procurement_requests_active_queue",
            "status",
            "updated_at",
            postgresql_where=text("status <> 'COMPLETED'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    status: Mapped[ProcurementStatus] = mapped_column(
        Enum(
            ProcurementStatus,
            name="procurement_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=30,
        ),
        nullable=False,
        default=ProcurementStatus.AGREEMENT_PENDING_MANAGER,
        server_default=ProcurementStatus.AGREEMENT_PENDING_MANAGER.value,
    )
    initiator_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_manager_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    creation_client_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    current_revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "procurement_revisions.id",
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_proc_requests_current_revision_proc_revisions",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=False,
        index=True,
    )
    final_movement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("movements.id", ondelete="RESTRICT"),
        unique=True,
    )
    state_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    revisions: Mapped[list[ProcurementRevision]] = relationship(
        back_populates="request",
        foreign_keys="ProcurementRevision.request_id",
        order_by="ProcurementRevision.revision_number",
        passive_deletes="all",
    )
    events: Mapped[list[ProcurementEvent]] = relationship(
        back_populates="request",
        order_by="ProcurementEvent.occurred_at, ProcurementEvent.id",
        passive_deletes="all",
    )


class ProcurementRevision(Base):
    __tablename__ = "procurement_revisions"
    __table_args__ = (
        UniqueConstraint("request_id", "revision_number", name="uq_procurement_revision_number"),
        UniqueConstraint("id", "request_id", name="uq_procurement_revision_id_request_id"),
        CheckConstraint("revision_number > 0", name="revision_number_positive"),
        CheckConstraint("line_count BETWEEN 1 AND 500", name="line_count_range"),
        CheckConstraint(
            "general_comment IS NULL OR btrim(general_comment) <> ''",
            name="general_comment_not_blank",
        ),
        Index("ix_procurement_revisions_request_created", "request_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("procurement_requests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    submitted_by_display_name_snapshot: Mapped[str] = mapped_column(String(579), nullable=False)
    general_comment: Mapped[str | None] = mapped_column(Text)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    request: Mapped[ProcurementRequest] = relationship(
        back_populates="revisions", foreign_keys=[request_id]
    )
    lines: Mapped[list[ProcurementRevisionLine]] = relationship(
        back_populates="revision",
        order_by="ProcurementRevisionLine.line_no",
        passive_deletes="all",
    )


class ProcurementRevisionLine(Base):
    __tablename__ = "procurement_revision_lines"
    __table_args__ = (
        UniqueConstraint("revision_id", "line_no", name="uq_procurement_revision_line_no"),
        CheckConstraint("line_no > 0", name="line_no_positive"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("line_type IN ('EXISTING_ITEM', 'PROPOSED_ITEM')", name="line_type"),
        CheckConstraint(
            "jsonb_typeof(display_snapshot) = 'object'", name="display_snapshot_object"
        ),
        CheckConstraint(
            "(line_type = 'EXISTING_ITEM' AND catalog_item_id IS NOT NULL) OR "
            "(line_type = 'PROPOSED_ITEM' AND catalog_item_id IS NULL)",
            name="catalog_item_shape",
        ),
        Index("ix_procurement_revision_lines_revision", "revision_id", "line_no"),
        Index("ix_procurement_revision_lines_catalog_item", "catalog_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("procurement_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    line_type: Mapped[ProcurementLineType] = mapped_column(
        Enum(
            ProcurementLineType,
            name="procurement_line_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=16,
        ),
        nullable=False,
    )
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("items.id", ondelete="RESTRICT")
    )
    display_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)

    revision: Mapped[ProcurementRevision] = relationship(back_populates="lines")
    binding: Mapped[ProcurementLineCatalogBinding | None] = relationship(
        back_populates="line", uselist=False, passive_deletes="all"
    )


class ProcurementLineCatalogBinding(Base):
    __tablename__ = "procurement_line_catalog_bindings"
    __table_args__ = (Index("ix_procurement_line_catalog_bindings_item", "item_id"),)

    revision_line_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("procurement_revision_lines.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    bound_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    bound_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    line: Mapped[ProcurementRevisionLine] = relationship(back_populates="binding")


class ProcurementEvent(Base):
    __tablename__ = "procurement_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('REQUEST_CREATED', 'REVISION_SUBMITTED', "
            "'MANAGER_ACCEPTED', 'CORRECTION_REQUESTED', 'ASSIGNMENT_TAKEN', "
            "'ASSIGNMENT_TRANSFERRED', 'TRANSFERRED_TO_ACCEPTANCE', 'LINE_BOUND', "
            "'DISCREPANCY_REPORTED', 'COMPLETED')",
            name="event_type",
        ),
        CheckConstraint("btrim(actor_display_name_snapshot) <> ''", name="actor_not_blank"),
        CheckConstraint("btrim(client_request_id) <> ''", name="client_request_id_not_blank"),
        CheckConstraint("length(request_fingerprint) = 64", name="request_fingerprint_length"),
        CheckConstraint("comment IS NULL OR btrim(comment) <> ''", name="comment_not_blank"),
        CheckConstraint(
            "metadata IS NULL OR jsonb_typeof(metadata) = 'object'", name="metadata_object"
        ),
        Index("ix_procurement_events_request_occurred", "request_id", "occurred_at", "id"),
        Index("ix_procurement_events_actor_occurred", "actor_user_id", "occurred_at"),
        UniqueConstraint(
            "request_id",
            "actor_user_id",
            "client_request_id",
            name="uq_procurement_events_request_actor_client_request",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("procurement_requests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[ProcurementEventType] = mapped_column(
        Enum(
            ProcurementEventType,
            name="procurement_event_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=31,
        ),
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    actor_display_name_snapshot: Mapped[str] = mapped_column(String(579), nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[ProcurementStatus | None] = mapped_column(
        Enum(
            ProcurementStatus,
            name="procurement_event_from_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=30,
        )
    )
    to_status: Mapped[ProcurementStatus | None] = mapped_column(
        Enum(
            ProcurementStatus,
            name="procurement_event_to_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=30,
        )
    )
    revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("procurement_revisions.id", ondelete="RESTRICT")
    )
    comment: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB(none_as_null=True),
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    request: Mapped[ProcurementRequest] = relationship(back_populates="events")


class EmailOutbox(Base):
    __tablename__ = "email_outbox"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'SENT', 'DEAD')", name="status"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("jsonb_typeof(to_addresses) = 'array'", name="to_addresses_array"),
        CheckConstraint("jsonb_typeof(cc_addresses) = 'array'", name="cc_addresses_array"),
        CheckConstraint("btrim(subject) <> ''", name="subject_not_blank"),
        CheckConstraint("btrim(text_body) <> ''", name="text_body_not_blank"),
        CheckConstraint("btrim(html_body) <> ''", name="html_body_not_blank"),
        CheckConstraint(
            "(claimed_at IS NULL AND claim_token IS NULL) OR "
            "(claimed_at IS NOT NULL AND claim_token IS NOT NULL)",
            name="claim_state",
        ),
        CheckConstraint(
            "(status = 'SENT' AND sent_at IS NOT NULL) OR (status <> 'SENT' AND sent_at IS NULL)",
            name="sent_state",
        ),
        Index("ix_email_outbox_delivery", "status", "available_at", "claimed_at"),
        Index("ix_email_outbox_status_updated", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("procurement_requests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    to_addresses: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    cc_addresses: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    text_body: Mapped[str] = mapped_column(Text, nullable=False)
    html_body: Mapped[str] = mapped_column(Text, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(8), nullable=False, default="PENDING", server_default="PENDING"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
