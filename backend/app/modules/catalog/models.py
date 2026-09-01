from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.catalog.enums import (
    AccountingMode,
    AttributeDataType,
    FilterType,
    ItemStatus,
)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("btrim(key) <> ''", name="key_not_blank"),
        CheckConstraint("btrim(display_name) <> ''", name="display_name_not_blank"),
        CheckConstraint(
            "default_accounting_mode IN ('QUANTITY', 'SERIAL')",
            name="default_accounting_mode",
        ),
        CheckConstraint("sort_order >= 0", name="sort_order_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    default_accounting_mode: Mapped[AccountingMode] = mapped_column(
        Enum(
            AccountingMode,
            name="accounting_mode",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=8,
        ),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
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

    attributes: Mapped[list[CategoryAttribute]] = relationship(
        back_populates="category",
        order_by="CategoryAttribute.sort_order",
    )
    items: Mapped[list[Item]] = relationship(back_populates="category")


class Manufacturer(Base):
    __tablename__ = "manufacturers"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint(
            "btrim(normalized_name) <> ''",
            name="normalized_name_not_blank",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
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

    items: Mapped[list[Item]] = relationship(
        back_populates="manufacturer",
        passive_deletes="all",
    )


class CategoryAttribute(Base):
    __tablename__ = "category_attributes"
    __table_args__ = (
        UniqueConstraint(
            "category_id",
            "key",
            name="uq_category_attributes_category_id_key",
        ),
        UniqueConstraint(
            "id",
            "category_id",
            name="uq_category_attributes_id_category_id",
        ),
        CheckConstraint("btrim(key) <> ''", name="key_not_blank"),
        CheckConstraint("btrim(label) <> ''", name="label_not_blank"),
        CheckConstraint(
            "data_type IN ('TEXT', 'INTEGER', 'DECIMAL', 'BOOLEAN', 'ENUM')",
            name="data_type",
        ),
        CheckConstraint(
            "filter_type IN ('NONE', 'EXACT', 'RANGE')",
            name="filter_type",
        ),
        CheckConstraint(
            "(filterable AND filter_type <> 'NONE') "
            "OR (NOT filterable AND filter_type = 'NONE')",
            name="filter_configuration",
        ),
        CheckConstraint(
            "CASE WHEN data_type = 'ENUM' THEN "
            "allowed_values IS NOT NULL "
            "AND jsonb_typeof(allowed_values) = 'array' "
            "AND jsonb_array_length(allowed_values) > 0 "
            "ELSE allowed_values IS NULL END",
            name="allowed_values_match_data_type",
        ),
        CheckConstraint(
            "validation_metadata IS NULL "
            "OR jsonb_typeof(validation_metadata) = 'object'",
            name="validation_metadata_object",
        ),
        CheckConstraint("sort_order >= 0", name="sort_order_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[AttributeDataType] = mapped_column(
        Enum(
            AttributeDataType,
            name="attribute_data_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=7,
        ),
        nullable=False,
    )
    unit: Mapped[str | None] = mapped_column(String(64))
    required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    filterable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    searchable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    card_visible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    detail_visible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    table_visible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    excel_visible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    filter_type: Mapped[FilterType] = mapped_column(
        Enum(
            FilterType,
            name="filter_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=5,
        ),
        nullable=False,
        default=FilterType.NONE,
        server_default=FilterType.NONE.value,
    )
    allowed_values: Mapped[list[str] | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    validation_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
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

    category: Mapped[Category] = relationship(back_populates="attributes")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "category_id",
            name="uq_items_id_category_id",
        ),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint(
            "btrim(normalized_name) <> ''",
            name="normalized_name_not_blank",
        ),
        CheckConstraint(
            "accounting_mode IN ('QUANTITY', 'SERIAL')",
            name="accounting_mode",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')",
            name="status",
        ),
        CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) "
            "OR (status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name="archive_state",
        ),
        Index(
            "ix_items_category_id_status_normalized_name",
            "category_id",
            "status",
            "normalized_name",
        ),
        Index(
            "ix_items_status_normalized_name",
            "status",
            "normalized_name",
        ),
        Index(
            "ix_items_duplicate_mpn",
            "category_id",
            "manufacturer_id",
            "normalized_manufacturer_part_number",
        ),
        Index(
            "ix_items_duplicate_name_model",
            "category_id",
            "manufacturer_id",
            "normalized_name",
            "normalized_model",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    manufacturer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("manufacturers.id", ondelete="RESTRICT"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str | None] = mapped_column(String(255))
    normalized_model: Mapped[str | None] = mapped_column(String(255))
    manufacturer_part_number: Mapped[str | None] = mapped_column(String(255))
    normalized_manufacturer_part_number: Mapped[str | None] = mapped_column(
        String(255)
    )
    internal_code: Mapped[str | None] = mapped_column(String(128))
    normalized_internal_code: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
    )
    description: Mapped[str | None] = mapped_column(Text)
    accounting_mode: Mapped[AccountingMode] = mapped_column(
        Enum(
            AccountingMode,
            name="accounting_mode",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=8,
        ),
        nullable=False,
    )
    status: Mapped[ItemStatus] = mapped_column(
        Enum(
            ItemStatus,
            name="item_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            length=8,
        ),
        nullable=False,
        default=ItemStatus.ACTIVE,
        server_default=ItemStatus.ACTIVE.value,
    )
    comment: Mapped[str | None] = mapped_column(Text)
    datasheet_url: Mapped[str | None] = mapped_column(String(2048))
    technical_data_source: Mapped[str | None] = mapped_column(Text)
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

    category: Mapped[Category] = relationship(back_populates="items")
    manufacturer: Mapped[Manufacturer | None] = relationship(back_populates="items")


class ItemAttributeValue(Base):
    __tablename__ = "item_attribute_values"
    __table_args__ = (
        ForeignKeyConstraint(
            ["item_id", "category_id"],
            ["items.id", "items.category_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["category_attribute_id", "category_id"],
            ["category_attributes.id", "category_attributes.category_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "item_id",
            "category_attribute_id",
            name="uq_item_attribute_values_item_id_category_attribute_id",
        ),
        CheckConstraint(
            "num_nonnulls(text_value, integer_value, decimal_value, "
            "boolean_value, enum_value) = 1",
            name="exactly_one_typed_value",
        ),
        CheckConstraint(
            "text_value IS NULL OR btrim(text_value) <> ''",
            name="text_value_not_blank",
        ),
        CheckConstraint(
            "enum_value IS NULL OR btrim(enum_value) <> ''",
            name="enum_value_not_blank",
        ),
        Index(
            "ix_item_attribute_values_category_attribute_id",
            "category_attribute_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    category_attribute_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    text_value: Mapped[str | None] = mapped_column(Text)
    integer_value: Mapped[int | None] = mapped_column(BigInteger)
    decimal_value: Mapped[Decimal | None] = mapped_column(Numeric(30, 10))
    boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    enum_value: Mapped[str | None] = mapped_column(String(255))
