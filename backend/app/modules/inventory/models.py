from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.inventory.enums import (
    LocationStatus,
    LocationType,
    MovementType,
)


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint("location_type IN ('WAREHOUSE', 'DATACENTER')", name="location_type"),
        CheckConstraint("btrim(code) <> ''", name="code_not_blank"),
        CheckConstraint(
            "btrim(normalized_code) <> ''",
            name="normalized_code_not_blank",
        ),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')",
            name="status",
        ),
        CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) "
            "OR (status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name="archive_state",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    location_type: Mapped[LocationType] = mapped_column(
        Enum(LocationType, native_enum=False, create_constraint=False, length=10),
        nullable=False,
    )
    status: Mapped[LocationStatus] = mapped_column(
        Enum(
            LocationStatus,
            name="location_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=8,
        ),
        nullable=False,
        default=LocationStatus.ACTIVE,
        server_default=LocationStatus.ACTIVE.value,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class Movement(Base):
    __tablename__ = "movements"
    __table_args__ = (
        CheckConstraint(
            "source_location_id IS NULL OR destination_location_id IS NULL "
            "OR source_location_id <> destination_location_id",
            name="positions_distinct",
        ),
        CheckConstraint(
            "(movement_type IN ('RECEIPT', 'RETURN') AND source_location_id IS NULL "
            "AND destination_location_id IS NOT NULL) OR "
            "(movement_type IN ('ISSUE', 'WRITE_OFF') AND source_location_id IS NOT NULL "
            "AND destination_location_id IS NULL) OR "
            "(movement_type = 'TRANSFER' AND source_location_id IS NOT NULL "
            "AND destination_location_id IS NOT NULL) OR "
            "(movement_type IN ('CORRECTION', 'REVERSAL') "
            "AND num_nonnulls(source_location_id, destination_location_id) BETWEEN 1 AND 2)",
            name="operation_positions",
        ),
        Index("ix_movements_actor_occurred", "actor_user_id", "occurred_at"),
        UniqueConstraint(
            "actor_user_id",
            "client_request_id",
            name="uq_movements_actor_user_id_client_request_id",
        ),
        UniqueConstraint(
            "journal_seq",
            name="uq_movements_journal_seq",
        ),
        CheckConstraint(
            "movement_type IN ('RECEIPT', 'ISSUE', 'RETURN', 'TRANSFER', "
            "'WRITE_OFF', 'CORRECTION', 'REVERSAL')",
            name="movement_type",
        ),
        CheckConstraint(
            "btrim(client_request_id) <> ''",
            name="client_request_id_not_blank",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64",
            name="request_fingerprint_length",
        ),
        CheckConstraint(
            "line_count BETWEEN 1 AND 500",
            name="line_count_range",
        ),
        CheckConstraint(
            "btrim(actor_display_name_snapshot) <> ''",
            name="actor_snapshot_not_blank",
        ),
        CheckConstraint(
            "((source_location_id IS NULL) = "
            "(source_location_code_snapshot IS NULL)) "
            "AND ((source_location_id IS NULL) = "
            "(source_location_name_snapshot IS NULL))",
            name="source_location_snapshot",
        ),
        CheckConstraint(
            "((destination_location_id IS NULL) = "
            "(destination_location_code_snapshot IS NULL)) "
            "AND ((destination_location_id IS NULL) = "
            "(destination_location_name_snapshot IS NULL))",
            name="destination_location_snapshot",
        ),
        CheckConstraint(
            "((movement_type IN ('CORRECTION', 'REVERSAL')) "
            "AND original_movement_id IS NOT NULL) "
            "OR ((movement_type NOT IN ('CORRECTION', 'REVERSAL')) "
            "AND original_movement_id IS NULL)",
            name="original_relationship",
        ),
        CheckConstraint(
            "original_movement_id IS NULL OR original_movement_id <> id",
            name="original_not_self",
        ),
        Index(
            "ux_movements_original_reversal",
            "original_movement_id",
            unique=True,
            postgresql_where=text("movement_type = 'REVERSAL'"),
        ),
        Index("ix_movements_occurred_at_id", "occurred_at", "id"),
        Index("ix_movements_original_movement_id", "original_movement_id"),
        Index("ix_movements_source_location_id", "source_location_id"),
        Index("ix_movements_destination_location_id", "destination_location_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    journal_seq: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        nullable=False,
    )
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    movement_type: Mapped[MovementType] = mapped_column(
        Enum(
            MovementType,
            name="movement_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=10,
        ),
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
    )
    destination_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
    )
    original_movement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("movements.id", ondelete="RESTRICT"),
    )
    client_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_display_name_snapshot: Mapped[str] = mapped_column(
        String(579),
        nullable=False,
    )
    source_location_code_snapshot: Mapped[str | None] = mapped_column(String(64))
    source_location_name_snapshot: Mapped[str | None] = mapped_column(String(255))
    destination_location_code_snapshot: Mapped[str | None] = mapped_column(String(64))
    destination_location_name_snapshot: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    lines: Mapped[list[MovementLine]] = relationship(
        back_populates="movement",
        passive_deletes="all",
        order_by="MovementLine.line_no",
    )


class MovementLine(Base):
    __tablename__ = "movement_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint("movement_id", "item_id", name="uq_movement_lines_movement_id_item_id"),
        UniqueConstraint(
            "movement_id",
            "line_no",
            name="uq_movement_lines_movement_id_line_no",
        ),
        CheckConstraint("line_no > 0", name="line_no_positive"),
        CheckConstraint(
            "btrim(item_name_snapshot) <> ''",
            name="item_name_snapshot_not_blank",
        ),
        Index("ix_movement_lines_item_id", "item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    movement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("movements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_no: Mapped[int] = mapped_column(nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    item_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    manufacturer_name_snapshot: Mapped[str | None] = mapped_column(String(255))
    model_snapshot: Mapped[str | None] = mapped_column(String(255))

    movement: Mapped[Movement] = relationship(back_populates="lines")


class StockBalance(Base):
    __tablename__ = "stock_balances"
    __table_args__ = (
        UniqueConstraint("item_id", "location_id", name="uq_stock_balances_item_id_location_id"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_stock_balances_location_id", "location_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
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
