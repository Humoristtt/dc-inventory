from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
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
from app.modules.catalog.enums import AccountingMode
from app.modules.inventory.enums import (
    InventoryUnitState,
    LocationStatus,
    MovementType,
)


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
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
    description: Mapped[str | None] = mapped_column(Text)
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


class InventoryUnit(Base):
    __tablename__ = "inventory_units"
    __table_args__ = (
        ForeignKeyConstraint(
            ["item_id", "item_accounting_mode"],
            ["items.id", "items.accounting_mode"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "id",
            "item_id",
            name="uq_inventory_units_id_item_id",
        ),
        UniqueConstraint(
            "item_id",
            "normalized_serial_number",
            name="uq_inventory_units_item_id_normalized_serial_number",
        ),
        UniqueConstraint(
            "normalized_wwn",
            name="uq_inventory_units_normalized_wwn",
        ),
        CheckConstraint(
            "item_accounting_mode = 'SERIAL'",
            name="serial_item_only",
        ),
        CheckConstraint("btrim(serial_number) <> ''", name="serial_number_not_blank"),
        CheckConstraint(
            "btrim(normalized_serial_number) <> ''",
            name="normalized_serial_number_not_blank",
        ),
        CheckConstraint("wwn IS NULL OR btrim(wwn) <> ''", name="wwn_not_blank"),
        CheckConstraint(
            "normalized_wwn IS NULL OR btrim(normalized_wwn) <> ''",
            name="normalized_wwn_not_blank",
        ),
        CheckConstraint(
            "state IN ('STORED', 'ISSUED', 'WRITTEN_OFF', 'VOIDED')",
            name="state",
        ),
        CheckConstraint(
            "(state = 'STORED' AND current_location_id IS NOT NULL "
            "AND current_holder_user_id IS NULL) "
            "OR (state = 'ISSUED' AND current_location_id IS NULL "
            "AND current_holder_user_id IS NOT NULL) "
            "OR (state IN ('WRITTEN_OFF', 'VOIDED') "
            "AND current_location_id IS NULL AND current_holder_user_id IS NULL)",
            name="current_position",
        ),
        Index("ix_inventory_units_state", "state"),
        Index("ix_inventory_units_current_location_id", "current_location_id"),
        Index(
            "ix_inventory_units_current_holder_user_id",
            "current_holder_user_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    item_accounting_mode: Mapped[AccountingMode] = mapped_column(
        Enum(
            AccountingMode,
            name="inventory_unit_accounting_mode",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=8,
        ),
        nullable=False,
        default=AccountingMode.SERIAL,
        server_default=AccountingMode.SERIAL.value,
    )
    serial_number: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_serial_number: Mapped[str] = mapped_column(String(255), nullable=False)
    wwn: Mapped[str | None] = mapped_column(String(255))
    normalized_wwn: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)
    state: Mapped[InventoryUnitState] = mapped_column(
        Enum(
            InventoryUnitState,
            name="inventory_unit_state",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=11,
        ),
        nullable=False,
    )
    current_location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
    )
    current_holder_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
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

    movement_lines: Mapped[list[MovementLine]] = relationship(
        back_populates="inventory_unit",
        passive_deletes="all",
    )


class Movement(Base):
    __tablename__ = "movements"
    __table_args__ = (
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
            "((source_holder_user_id IS NULL) = (source_holder_display_name_snapshot IS NULL))",
            name="source_holder_snapshot",
        ),
        CheckConstraint(
            "((destination_holder_user_id IS NULL) = "
            "(destination_holder_display_name_snapshot IS NULL))",
            name="destination_holder_snapshot",
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
        CheckConstraint(
            "num_nonnulls(source_location_id, source_holder_user_id) <= 1 "
            "AND num_nonnulls(destination_location_id, "
            "destination_holder_user_id) <= 1",
            name="position_side_exclusive",
        ),
        CheckConstraint(
            "NOT (source_location_id IS NOT NULL "
            "AND source_location_id = destination_location_id) "
            "AND NOT (source_holder_user_id IS NOT NULL "
            "AND source_holder_user_id = destination_holder_user_id)",
            name="positions_distinct",
        ),
        CheckConstraint(
            "(movement_type = 'RECEIPT' "
            "AND source_location_id IS NULL "
            "AND source_holder_user_id IS NULL "
            "AND destination_location_id IS NOT NULL "
            "AND destination_holder_user_id IS NULL) "
            "OR (movement_type = 'ISSUE' "
            "AND source_location_id IS NOT NULL "
            "AND source_holder_user_id IS NULL "
            "AND destination_location_id IS NULL "
            "AND destination_holder_user_id IS NOT NULL) "
            "OR (movement_type = 'RETURN' "
            "AND source_location_id IS NULL "
            "AND source_holder_user_id IS NOT NULL "
            "AND destination_location_id IS NOT NULL "
            "AND destination_holder_user_id IS NULL) "
            "OR (movement_type = 'TRANSFER' "
            "AND source_location_id IS NOT NULL "
            "AND source_holder_user_id IS NULL "
            "AND destination_location_id IS NOT NULL "
            "AND destination_holder_user_id IS NULL) "
            "OR (movement_type = 'WRITE_OFF' "
            "AND num_nonnulls(source_location_id, source_holder_user_id) = 1 "
            "AND destination_location_id IS NULL "
            "AND destination_holder_user_id IS NULL) "
            "OR (movement_type IN ('CORRECTION', 'REVERSAL') "
            "AND num_nonnulls(source_location_id, source_holder_user_id, "
            "destination_location_id, destination_holder_user_id) "
            "BETWEEN 1 AND 2)",
            name="operation_positions",
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
        Index("ix_movements_source_holder_user_id", "source_holder_user_id"),
        Index(
            "ix_movements_destination_holder_user_id",
            "destination_holder_user_id",
        ),
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
    source_holder_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    destination_holder_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    original_movement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("movements.id", ondelete="RESTRICT"),
    )
    client_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)
    actor_display_name_snapshot: Mapped[str] = mapped_column(
        String(579),
        nullable=False,
    )
    source_holder_display_name_snapshot: Mapped[str | None] = mapped_column(String(579))
    destination_holder_display_name_snapshot: Mapped[str | None] = mapped_column(String(579))
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
        ForeignKeyConstraint(
            ["item_id", "item_accounting_mode"],
            ["items.id", "items.accounting_mode"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["inventory_unit_id", "item_id"],
            ["inventory_units.id", "inventory_units.item_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "movement_id",
            "inventory_unit_id",
            name="uq_movement_lines_movement_id_inventory_unit_id",
        ),
        UniqueConstraint(
            "movement_id",
            "line_no",
            name="uq_movement_lines_movement_id_line_no",
        ),
        CheckConstraint("line_no > 0", name="line_no_positive"),
        CheckConstraint(
            "item_accounting_mode IN ('QUANTITY', 'SERIAL')",
            name="item_accounting_mode",
        ),
        CheckConstraint(
            "(item_accounting_mode = 'QUANTITY' "
            "AND quantity IS NOT NULL AND quantity > 0 "
            "AND inventory_unit_id IS NULL AND serial_number_snapshot IS NULL "
            "AND wwn_snapshot IS NULL) "
            "OR (item_accounting_mode = 'SERIAL' AND quantity IS NULL "
            "AND inventory_unit_id IS NOT NULL "
            "AND serial_number_snapshot IS NOT NULL "
            "AND btrim(serial_number_snapshot) <> '' "
            "AND (wwn_snapshot IS NULL OR btrim(wwn_snapshot) <> ''))",
            name="accounting_shape",
        ),
        CheckConstraint(
            "btrim(item_name_snapshot) <> ''",
            name="item_name_snapshot_not_blank",
        ),
        Index(
            "ux_movement_lines_quantity_item",
            "movement_id",
            "item_id",
            unique=True,
            postgresql_where=text("item_accounting_mode = 'QUANTITY'"),
        ),
        Index("ix_movement_lines_item_id", "item_id"),
        Index("ix_movement_lines_inventory_unit_id", "inventory_unit_id"),
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
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    item_accounting_mode: Mapped[AccountingMode] = mapped_column(
        Enum(
            AccountingMode,
            name="movement_line_accounting_mode",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=8,
        ),
        nullable=False,
    )
    inventory_unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    quantity: Mapped[int | None] = mapped_column(BigInteger)
    item_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    manufacturer_name_snapshot: Mapped[str | None] = mapped_column(String(255))
    model_snapshot: Mapped[str | None] = mapped_column(String(255))
    manufacturer_part_number_snapshot: Mapped[str | None] = mapped_column(String(255))
    serial_number_snapshot: Mapped[str | None] = mapped_column(String(255))
    wwn_snapshot: Mapped[str | None] = mapped_column(String(255))

    movement: Mapped[Movement] = relationship(back_populates="lines")
    inventory_unit: Mapped[InventoryUnit | None] = relationship(back_populates="movement_lines")


class StockBalance(Base):
    __tablename__ = "stock_balances"
    __table_args__ = (
        ForeignKeyConstraint(
            ["item_id", "item_accounting_mode"],
            ["items.id", "items.accounting_mode"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "item_accounting_mode = 'QUANTITY'",
            name="quantity_item_only",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "num_nonnulls(location_id, holder_user_id) = 1",
            name="single_position",
        ),
        Index(
            "ux_stock_balances_item_location",
            "item_id",
            "location_id",
            unique=True,
            postgresql_where=text("holder_user_id IS NULL"),
        ),
        Index(
            "ux_stock_balances_item_holder",
            "item_id",
            "holder_user_id",
            unique=True,
            postgresql_where=text("location_id IS NULL"),
        ),
        Index("ix_stock_balances_location_id", "location_id"),
        Index("ix_stock_balances_holder_user_id", "holder_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    item_accounting_mode: Mapped[AccountingMode] = mapped_column(
        Enum(
            AccountingMode,
            name="stock_balance_accounting_mode",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=8,
        ),
        nullable=False,
        default=AccountingMode.QUANTITY,
        server_default=AccountingMode.QUANTITY.value,
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
    )
    holder_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
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
