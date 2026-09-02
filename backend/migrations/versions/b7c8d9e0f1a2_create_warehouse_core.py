"""Создать warehouse ledger и транзакционные current-state projections.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | Sequence[str] | None = "a6b7c8d9e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_items_id_accounting_mode",
        "items",
        ["id", "accounting_mode"],
    )

    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("normalized_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=8),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            "btrim(code) <> ''",
            name=op.f("ck_locations_code_not_blank"),
        ),
        sa.CheckConstraint(
            "btrim(normalized_code) <> ''",
            name=op.f("ck_locations_normalized_code_not_blank"),
        ),
        sa.CheckConstraint(
            "btrim(name) <> ''",
            name=op.f("ck_locations_name_not_blank"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')",
            name=op.f("ck_locations_status"),
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) "
            "OR (status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name=op.f("ck_locations_archive_state"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locations")),
        sa.UniqueConstraint(
            "normalized_code",
            name=op.f("uq_locations_normalized_code"),
        ),
    )

    op.create_table(
        "inventory_units",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column(
            "item_accounting_mode",
            sa.String(length=8),
            server_default=sa.text("'SERIAL'"),
            nullable=False,
        ),
        sa.Column("serial_number", sa.String(length=255), nullable=False),
        sa.Column(
            "normalized_serial_number",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column("wwn", sa.String(length=255), nullable=True),
        sa.Column("normalized_wwn", sa.String(length=255), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=11), nullable=False),
        sa.Column("current_location_id", sa.Uuid(), nullable=True),
        sa.Column("current_holder_user_id", sa.Uuid(), nullable=True),
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
            "item_accounting_mode = 'SERIAL'",
            name=op.f("ck_inventory_units_serial_item_only"),
        ),
        sa.CheckConstraint(
            "btrim(serial_number) <> ''",
            name=op.f("ck_inventory_units_serial_number_not_blank"),
        ),
        sa.CheckConstraint(
            "btrim(normalized_serial_number) <> ''",
            name=op.f("ck_inventory_units_normalized_serial_number_not_blank"),
        ),
        sa.CheckConstraint(
            "wwn IS NULL OR btrim(wwn) <> ''",
            name=op.f("ck_inventory_units_wwn_not_blank"),
        ),
        sa.CheckConstraint(
            "normalized_wwn IS NULL OR btrim(normalized_wwn) <> ''",
            name=op.f("ck_inventory_units_normalized_wwn_not_blank"),
        ),
        sa.CheckConstraint(
            "state IN ('STORED', 'ISSUED', 'WRITTEN_OFF', 'VOIDED')",
            name=op.f("ck_inventory_units_state"),
        ),
        sa.CheckConstraint(
            "(state = 'STORED' AND current_location_id IS NOT NULL "
            "AND current_holder_user_id IS NULL) "
            "OR (state = 'ISSUED' AND current_location_id IS NULL "
            "AND current_holder_user_id IS NOT NULL) "
            "OR (state IN ('WRITTEN_OFF', 'VOIDED') "
            "AND current_location_id IS NULL AND current_holder_user_id IS NULL)",
            name=op.f("ck_inventory_units_current_position"),
        ),
        sa.ForeignKeyConstraint(
            ["current_holder_user_id"],
            ["users.id"],
            name=op.f("fk_inventory_units_current_holder_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_location_id"],
            ["locations.id"],
            name=op.f("fk_inventory_units_current_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "item_accounting_mode"],
            ["items.id", "items.accounting_mode"],
            name=op.f("fk_inventory_units_item_id_items"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_units")),
        sa.UniqueConstraint(
            "id",
            "item_id",
            name="uq_inventory_units_id_item_id",
        ),
        sa.UniqueConstraint(
            "item_id",
            "normalized_serial_number",
            name="uq_inventory_units_item_id_normalized_serial_number",
        ),
        sa.UniqueConstraint(
            "normalized_wwn",
            name="uq_inventory_units_normalized_wwn",
        ),
    )
    op.create_index(
        "ix_inventory_units_state",
        "inventory_units",
        ["state"],
        unique=False,
    )
    op.create_index(
        "ix_inventory_units_current_location_id",
        "inventory_units",
        ["current_location_id"],
        unique=False,
    )
    op.create_index(
        "ix_inventory_units_current_holder_user_id",
        "inventory_units",
        ["current_holder_user_id"],
        unique=False,
    )

    op.create_table(
        "movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "journal_seq",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("movement_type", sa.String(length=10), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("source_location_id", sa.Uuid(), nullable=True),
        sa.Column("destination_location_id", sa.Uuid(), nullable=True),
        sa.Column("source_holder_user_id", sa.Uuid(), nullable=True),
        sa.Column("destination_holder_user_id", sa.Uuid(), nullable=True),
        sa.Column("original_movement_id", sa.Uuid(), nullable=True),
        sa.Column("client_request_id", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=255), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "actor_display_name_snapshot",
            sa.String(length=579),
            nullable=False,
        ),
        sa.Column(
            "source_holder_display_name_snapshot",
            sa.String(length=579),
            nullable=True,
        ),
        sa.Column(
            "destination_holder_display_name_snapshot",
            sa.String(length=579),
            nullable=True,
        ),
        sa.Column(
            "source_location_code_snapshot",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "source_location_name_snapshot",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "destination_location_code_snapshot",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "destination_location_name_snapshot",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "movement_type IN ('RECEIPT', 'ISSUE', 'RETURN', 'TRANSFER', "
            "'WRITE_OFF', 'CORRECTION', 'REVERSAL')",
            name=op.f("ck_movements_movement_type"),
        ),
        sa.CheckConstraint(
            "btrim(client_request_id) <> ''",
            name=op.f("ck_movements_client_request_id_not_blank"),
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name=op.f("ck_movements_request_fingerprint_length"),
        ),
        sa.CheckConstraint(
            "line_count BETWEEN 1 AND 500",
            name=op.f("ck_movements_line_count_range"),
        ),
        sa.CheckConstraint(
            "btrim(actor_display_name_snapshot) <> ''",
            name=op.f("ck_movements_actor_snapshot_not_blank"),
        ),
        sa.CheckConstraint(
            "((source_location_id IS NULL) = "
            "(source_location_code_snapshot IS NULL)) "
            "AND ((source_location_id IS NULL) = "
            "(source_location_name_snapshot IS NULL))",
            name=op.f("ck_movements_source_location_snapshot"),
        ),
        sa.CheckConstraint(
            "((destination_location_id IS NULL) = "
            "(destination_location_code_snapshot IS NULL)) "
            "AND ((destination_location_id IS NULL) = "
            "(destination_location_name_snapshot IS NULL))",
            name=op.f("ck_movements_destination_location_snapshot"),
        ),
        sa.CheckConstraint(
            "((source_holder_user_id IS NULL) = (source_holder_display_name_snapshot IS NULL))",
            name=op.f("ck_movements_source_holder_snapshot"),
        ),
        sa.CheckConstraint(
            "((destination_holder_user_id IS NULL) = "
            "(destination_holder_display_name_snapshot IS NULL))",
            name=op.f("ck_movements_destination_holder_snapshot"),
        ),
        sa.CheckConstraint(
            "((movement_type IN ('CORRECTION', 'REVERSAL')) "
            "AND original_movement_id IS NOT NULL) "
            "OR ((movement_type NOT IN ('CORRECTION', 'REVERSAL')) "
            "AND original_movement_id IS NULL)",
            name=op.f("ck_movements_original_relationship"),
        ),
        sa.CheckConstraint(
            "original_movement_id IS NULL OR original_movement_id <> id",
            name=op.f("ck_movements_original_not_self"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(source_location_id, source_holder_user_id) <= 1 "
            "AND num_nonnulls(destination_location_id, "
            "destination_holder_user_id) <= 1",
            name=op.f("ck_movements_position_side_exclusive"),
        ),
        sa.CheckConstraint(
            "NOT (source_location_id IS NOT NULL "
            "AND source_location_id = destination_location_id) "
            "AND NOT (source_holder_user_id IS NOT NULL "
            "AND source_holder_user_id = destination_holder_user_id)",
            name=op.f("ck_movements_positions_distinct"),
        ),
        sa.CheckConstraint(
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
            name=op.f("ck_movements_operation_positions"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_movements_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["destination_holder_user_id"],
            ["users.id"],
            name=op.f("fk_movements_destination_holder_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["destination_location_id"],
            ["locations.id"],
            name=op.f("fk_movements_destination_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["original_movement_id"],
            ["movements.id"],
            name=op.f("fk_movements_original_movement_id_movements"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_holder_user_id"],
            ["users.id"],
            name=op.f("fk_movements_source_holder_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_location_id"],
            ["locations.id"],
            name=op.f("fk_movements_source_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movements")),
        sa.UniqueConstraint(
            "journal_seq",
            name="uq_movements_journal_seq",
        ),
        sa.UniqueConstraint(
            "actor_user_id",
            "client_request_id",
            name="uq_movements_actor_user_id_client_request_id",
        ),
    )
    op.create_index(
        "ux_movements_original_reversal",
        "movements",
        ["original_movement_id"],
        unique=True,
        postgresql_where=sa.text("movement_type = 'REVERSAL'"),
    )
    for index_name, columns in (
        ("ix_movements_occurred_at_id", ["occurred_at", "id"]),
        ("ix_movements_original_movement_id", ["original_movement_id"]),
        ("ix_movements_source_location_id", ["source_location_id"]),
        ("ix_movements_destination_location_id", ["destination_location_id"]),
        ("ix_movements_source_holder_user_id", ["source_holder_user_id"]),
        (
            "ix_movements_destination_holder_user_id",
            ["destination_holder_user_id"],
        ),
    ):
        op.create_index(index_name, "movements", columns, unique=False)

    op.create_table(
        "movement_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("movement_id", sa.Uuid(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("item_accounting_mode", sa.String(length=8), nullable=False),
        sa.Column("inventory_unit_id", sa.Uuid(), nullable=True),
        sa.Column("quantity", sa.BigInteger(), nullable=True),
        sa.Column("item_name_snapshot", sa.String(length=255), nullable=False),
        sa.Column(
            "manufacturer_name_snapshot",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column("model_snapshot", sa.String(length=255), nullable=True),
        sa.Column(
            "manufacturer_part_number_snapshot",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "serial_number_snapshot",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column("wwn_snapshot", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "line_no > 0",
            name=op.f("ck_movement_lines_line_no_positive"),
        ),
        sa.CheckConstraint(
            "item_accounting_mode IN ('QUANTITY', 'SERIAL')",
            name=op.f("ck_movement_lines_item_accounting_mode"),
        ),
        sa.CheckConstraint(
            "(item_accounting_mode = 'QUANTITY' "
            "AND quantity IS NOT NULL AND quantity > 0 "
            "AND inventory_unit_id IS NULL AND serial_number_snapshot IS NULL "
            "AND wwn_snapshot IS NULL) "
            "OR (item_accounting_mode = 'SERIAL' AND quantity IS NULL "
            "AND inventory_unit_id IS NOT NULL "
            "AND serial_number_snapshot IS NOT NULL "
            "AND btrim(serial_number_snapshot) <> '' "
            "AND (wwn_snapshot IS NULL OR btrim(wwn_snapshot) <> ''))",
            name=op.f("ck_movement_lines_accounting_shape"),
        ),
        sa.CheckConstraint(
            "btrim(item_name_snapshot) <> ''",
            name=op.f("ck_movement_lines_item_name_snapshot_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["inventory_unit_id", "item_id"],
            ["inventory_units.id", "inventory_units.item_id"],
            name=op.f("fk_movement_lines_inventory_unit_id_inventory_units"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "item_accounting_mode"],
            ["items.id", "items.accounting_mode"],
            name=op.f("fk_movement_lines_item_id_items"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["movement_id"],
            ["movements.id"],
            name=op.f("fk_movement_lines_movement_id_movements"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movement_lines")),
        sa.UniqueConstraint(
            "movement_id",
            "inventory_unit_id",
            name="uq_movement_lines_movement_id_inventory_unit_id",
        ),
        sa.UniqueConstraint(
            "movement_id",
            "line_no",
            name="uq_movement_lines_movement_id_line_no",
        ),
    )
    op.create_index(
        "ux_movement_lines_quantity_item",
        "movement_lines",
        ["movement_id", "item_id"],
        unique=True,
        postgresql_where=sa.text("item_accounting_mode = 'QUANTITY'"),
    )
    op.create_index(
        "ix_movement_lines_item_id",
        "movement_lines",
        ["item_id"],
        unique=False,
    )
    op.create_index(
        "ix_movement_lines_inventory_unit_id",
        "movement_lines",
        ["inventory_unit_id"],
        unique=False,
    )

    op.create_table(
        "stock_balances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column(
            "item_accounting_mode",
            sa.String(length=8),
            server_default=sa.text("'QUANTITY'"),
            nullable=False,
        ),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("holder_user_id", sa.Uuid(), nullable=True),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
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
            "item_accounting_mode = 'QUANTITY'",
            name=op.f("ck_stock_balances_quantity_item_only"),
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name=op.f("ck_stock_balances_quantity_positive"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(location_id, holder_user_id) = 1",
            name=op.f("ck_stock_balances_single_position"),
        ),
        sa.ForeignKeyConstraint(
            ["holder_user_id"],
            ["users.id"],
            name=op.f("fk_stock_balances_holder_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "item_accounting_mode"],
            ["items.id", "items.accounting_mode"],
            name=op.f("fk_stock_balances_item_id_items"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_stock_balances_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_balances")),
    )
    op.create_index(
        "ux_stock_balances_item_location",
        "stock_balances",
        ["item_id", "location_id"],
        unique=True,
        postgresql_where=sa.text("holder_user_id IS NULL"),
    )
    op.create_index(
        "ux_stock_balances_item_holder",
        "stock_balances",
        ["item_id", "holder_user_id"],
        unique=True,
        postgresql_where=sa.text("location_id IS NULL"),
    )
    op.create_index(
        "ix_stock_balances_location_id",
        "stock_balances",
        ["location_id"],
        unique=False,
    )
    op.create_index(
        "ix_stock_balances_holder_user_id",
        "stock_balances",
        ["holder_user_id"],
        unique=False,
    )

    op.execute(
        """
        CREATE FUNCTION validate_warehouse_correction_header()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            original movements%ROWTYPE;
        BEGIN
            IF NEW.movement_type <> 'CORRECTION' THEN
                RETURN NEW;
            END IF;

            SELECT * INTO original
            FROM movements
            WHERE id = NEW.original_movement_id;

            IF NOT FOUND OR original.movement_type = 'REVERSAL' THEN
                RAISE EXCEPTION 'invalid correction target'
                    USING ERRCODE = '23514';
            END IF;

            IF NOT coalesce((
                (NEW.source_location_id IS NOT NULL AND (
                    NEW.source_location_id = original.source_location_id OR
                    NEW.source_location_id = original.destination_location_id
                )) OR
                (NEW.destination_location_id IS NOT NULL AND (
                    NEW.destination_location_id = original.source_location_id OR
                    NEW.destination_location_id = original.destination_location_id
                )) OR
                (NEW.source_holder_user_id IS NOT NULL AND (
                    NEW.source_holder_user_id = original.source_holder_user_id OR
                    NEW.source_holder_user_id = original.destination_holder_user_id
                )) OR
                (NEW.destination_holder_user_id IS NOT NULL AND (
                    NEW.destination_holder_user_id = original.source_holder_user_id OR
                    NEW.destination_holder_user_id = original.destination_holder_user_id
                ))
            ), false) THEN
                RAISE EXCEPTION 'correction does not concern an original position'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_movements_validate_correction
        BEFORE INSERT ON movements
        FOR EACH ROW EXECUTE FUNCTION validate_warehouse_correction_header()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_warehouse_correction_line()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            movement_type_value varchar(10);
            original_id uuid;
        BEGIN
            SELECT movement_type, original_movement_id
            INTO movement_type_value, original_id
            FROM movements
            WHERE id = NEW.movement_id;

            IF movement_type_value = 'CORRECTION' AND NOT EXISTS (
                SELECT 1
                FROM movement_lines
                WHERE movement_id = original_id
                  AND item_id = NEW.item_id
            ) THEN
                RAISE EXCEPTION 'correction line does not concern an original item'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_movement_lines_validate_correction
        BEFORE INSERT ON movement_lines
        FOR EACH ROW EXECUTE FUNCTION validate_warehouse_correction_line()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_warehouse_movement_line_count()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            target_movement_id uuid;
            expected_count integer;
            actual_count bigint;
            minimum_line integer;
            maximum_line integer;
        BEGIN
            IF TG_TABLE_NAME = 'movements' THEN
                target_movement_id := NEW.id;
            ELSE
                target_movement_id := NEW.movement_id;
            END IF;

            SELECT line_count
            INTO expected_count
            FROM movements
            WHERE id = target_movement_id;

            IF expected_count IS NULL THEN
                RAISE EXCEPTION 'movement header is unavailable for line cardinality check'
                    USING ERRCODE = '23514';
            END IF;

            SELECT count(*), min(line_no), max(line_no)
            INTO actual_count, minimum_line, maximum_line
            FROM movement_lines
            WHERE movement_id = target_movement_id;

            IF actual_count <> expected_count
               OR minimum_line IS DISTINCT FROM 1
               OR maximum_line IS DISTINCT FROM expected_count THEN
                RAISE EXCEPTION 'movement line cardinality does not match sealed header'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_movements_validate_line_count
        AFTER INSERT ON movements
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION validate_warehouse_movement_line_count()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_movement_lines_validate_line_count
        AFTER INSERT ON movement_lines
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION validate_warehouse_movement_line_count()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_warehouse_history_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'committed warehouse history is append-only'
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_movements_append_only
        BEFORE UPDATE OR DELETE ON movements
        FOR EACH ROW EXECUTE FUNCTION reject_warehouse_history_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_movement_lines_append_only
        BEFORE UPDATE OR DELETE ON movement_lines
        FOR EACH ROW EXECUTE FUNCTION reject_warehouse_history_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_movements_append_only_truncate
        BEFORE TRUNCATE ON movements
        FOR EACH STATEMENT EXECUTE FUNCTION reject_warehouse_history_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_movement_lines_append_only_truncate
        BEFORE TRUNCATE ON movement_lines
        FOR EACH STATEMENT EXECUTE FUNCTION reject_warehouse_history_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_movement_lines_validate_line_count "
        "ON movement_lines"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_movements_validate_line_count ON movements"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS validate_warehouse_movement_line_count()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_movement_lines_validate_correction "
        "ON movement_lines"
    )
    op.execute("DROP FUNCTION IF EXISTS validate_warehouse_correction_line()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_movements_validate_correction ON movements"
    )
    op.execute("DROP FUNCTION IF EXISTS validate_warehouse_correction_header()")
    op.execute(
        "DROP TRIGGER trg_movement_lines_append_only_truncate ON movement_lines"
    )
    op.execute(
        "DROP TRIGGER trg_movements_append_only_truncate ON movements"
    )
    op.execute("DROP TRIGGER trg_movement_lines_append_only ON movement_lines")
    op.execute("DROP TRIGGER trg_movements_append_only ON movements")
    op.execute("DROP FUNCTION reject_warehouse_history_mutation()")

    op.drop_index(
        "ix_stock_balances_holder_user_id",
        table_name="stock_balances",
    )
    op.drop_index("ix_stock_balances_location_id", table_name="stock_balances")
    op.drop_index("ux_stock_balances_item_holder", table_name="stock_balances")
    op.drop_index("ux_stock_balances_item_location", table_name="stock_balances")
    op.drop_table("stock_balances")

    op.drop_index(
        "ix_movement_lines_inventory_unit_id",
        table_name="movement_lines",
    )
    op.drop_index("ix_movement_lines_item_id", table_name="movement_lines")
    op.drop_index(
        "ux_movement_lines_quantity_item",
        table_name="movement_lines",
    )
    op.drop_table("movement_lines")

    op.drop_index(
        "ix_movements_destination_holder_user_id",
        table_name="movements",
    )
    op.drop_index("ix_movements_source_holder_user_id", table_name="movements")
    op.drop_index(
        "ix_movements_destination_location_id",
        table_name="movements",
    )
    op.drop_index("ix_movements_source_location_id", table_name="movements")
    op.drop_index("ix_movements_original_movement_id", table_name="movements")
    op.drop_index("ix_movements_occurred_at_id", table_name="movements")
    op.drop_index("ux_movements_original_reversal", table_name="movements")
    op.drop_table("movements")

    op.drop_index(
        "ix_inventory_units_current_holder_user_id",
        table_name="inventory_units",
    )
    op.drop_index(
        "ix_inventory_units_current_location_id",
        table_name="inventory_units",
    )
    op.drop_index("ix_inventory_units_state", table_name="inventory_units")
    op.drop_table("inventory_units")
    op.drop_table("locations")

    op.drop_constraint("uq_items_id_accounting_mode", "items", type_="unique")
