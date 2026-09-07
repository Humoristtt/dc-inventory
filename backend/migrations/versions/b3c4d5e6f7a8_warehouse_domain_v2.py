"""warehouse_domain_v2

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-09-07 15:26:53.708590
"""

import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b3c4d5e6f7a8'
down_revision: str | Sequence[str] | None = 'a2b3c4d5e6f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _guard_upgrade()
    # No user/catalog data is discarded: the stage requires an empty domain.
    op.execute("DELETE FROM category_attributes")
    op.execute("DELETE FROM categories")
    op.drop_constraint(op.f('fk_movement_lines_inventory_unit_id_inventory_units'), 'movement_lines', type_='foreignkey')
    op.drop_constraint(op.f('fk_movement_lines_item_id_items'), 'movement_lines', type_='foreignkey')
    op.drop_constraint(op.f('fk_stock_balances_item_id_items'), 'stock_balances', type_='foreignkey')
    op.drop_constraint(op.f('ck_movements_operation_positions'), 'movements', type_='check')
    op.drop_constraint(op.f('ck_movements_positions_distinct'), 'movements', type_='check')
    op.drop_index(op.f('ix_inventory_units_current_holder_user_id'), table_name='inventory_units')
    op.drop_index(op.f('ix_inventory_units_current_location_id'), table_name='inventory_units')
    op.drop_index(op.f('ix_inventory_units_item_state_location'), table_name='inventory_units')
    op.drop_index(op.f('ix_inventory_units_normalized_serial_trgm'), table_name='inventory_units', postgresql_ops={'normalized_serial_number': 'gin_trgm_ops'}, postgresql_using='gin')
    op.drop_index(op.f('ix_inventory_units_normalized_wwn_trgm'), table_name='inventory_units', postgresql_ops={'normalized_wwn': 'gin_trgm_ops'}, postgresql_using='gin')
    op.drop_index(op.f('ix_inventory_units_state'), table_name='inventory_units')
    op.drop_table('inventory_units')
    op.add_column('categories', sa.Column('parent_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_categories_parent_id'), 'categories', ['parent_id'], unique=False)
    op.create_foreign_key(op.f('fk_categories_parent_id_categories'), 'categories', 'categories', ['parent_id'], ['id'], ondelete='RESTRICT')
    op.drop_constraint(op.f('ck_categories_default_accounting_mode'), 'categories', type_='check')
    op.drop_column('categories', 'default_accounting_mode')
    op.add_column('items', sa.Column('identity_signature', sa.String(length=64), nullable=False))
    op.drop_index(op.f('ix_items_duplicate_mpn'), table_name='items')
    op.drop_index(op.f('ix_items_normalized_internal_code_trgm'), table_name='items', postgresql_ops={'normalized_internal_code': 'gin_trgm_ops'}, postgresql_using='gin')
    op.drop_index(op.f('ix_items_normalized_mpn_trgm'), table_name='items', postgresql_ops={'normalized_manufacturer_part_number': 'gin_trgm_ops'}, postgresql_using='gin')
    op.drop_constraint(op.f('uq_items_id_accounting_mode'), 'items', type_='unique')
    op.drop_constraint(op.f('uq_items_normalized_internal_code'), 'items', type_='unique')
    op.create_unique_constraint(op.f('uq_items_identity_signature'), 'items', ['identity_signature'])
    op.drop_constraint(op.f('ck_items_accounting_mode'), 'items', type_='check')
    op.drop_column('items', 'datasheet_url')
    op.drop_column('items', 'manufacturer_part_number')
    op.drop_column('items', 'normalized_manufacturer_part_number')
    op.drop_column('items', 'accounting_mode')
    op.drop_column('items', 'comment')
    op.drop_column('items', 'description')
    op.drop_column('items', 'normalized_internal_code')
    op.drop_column('items', 'internal_code')
    op.drop_column('items', 'technical_data_source')
    op.add_column('locations', sa.Column('address', sa.Text(), nullable=True))
    op.add_column('locations', sa.Column('location_type', sa.Enum('WAREHOUSE', 'DATACENTER', name='locationtype', native_enum=False), nullable=False))
    op.create_check_constraint(op.f('ck_locations_location_type'), 'locations', "location_type IN ('WAREHOUSE', 'DATACENTER')")
    op.drop_column('locations', 'description')
    op.alter_column('movement_lines', 'quantity',
                   existing_type=sa.BIGINT(),
                   nullable=False)
    op.drop_index(op.f('ix_movement_lines_inventory_unit_id'), table_name='movement_lines')
    op.drop_constraint(op.f('uq_movement_lines_movement_id_inventory_unit_id'), 'movement_lines', type_='unique')
    op.drop_index(op.f('ux_movement_lines_quantity_item'), table_name='movement_lines', postgresql_where="((item_accounting_mode)::text = 'QUANTITY'::text)")
    op.create_unique_constraint('uq_movement_lines_movement_id_item_id', 'movement_lines', ['movement_id', 'item_id'])
    op.create_foreign_key(op.f('fk_movement_lines_item_id_items'), 'movement_lines', 'items', ['item_id'], ['id'], ondelete='RESTRICT')
    op.drop_constraint(op.f('ck_movement_lines_accounting_shape'), 'movement_lines', type_='check')
    op.drop_constraint(op.f('ck_movement_lines_item_accounting_mode'), 'movement_lines', type_='check')
    op.create_check_constraint(op.f('ck_movement_lines_quantity_positive'), 'movement_lines', 'quantity > 0')
    op.drop_column('movement_lines', 'item_accounting_mode')
    op.drop_column('movement_lines', 'inventory_unit_id')
    op.drop_column('movement_lines', 'manufacturer_part_number_snapshot')
    op.drop_column('movement_lines', 'serial_number_snapshot')
    op.drop_column('movement_lines', 'wwn_snapshot')
    op.drop_index(op.f('ix_movements_destination_holder_user_id'), table_name='movements')
    op.drop_index(op.f('ix_movements_source_holder_user_id'), table_name='movements')
    op.create_index('ix_movements_actor_occurred', 'movements', ['actor_user_id', 'occurred_at'], unique=False)
    op.drop_constraint(op.f('fk_movements_destination_holder_user_id_users'), 'movements', type_='foreignkey')
    op.drop_constraint(op.f('fk_movements_source_holder_user_id_users'), 'movements', type_='foreignkey')
    op.drop_constraint(op.f('ck_movements_destination_holder_snapshot'), 'movements', type_='check')
    op.drop_constraint(op.f('ck_movements_position_side_exclusive'), 'movements', type_='check')
    op.drop_constraint(op.f('ck_movements_source_holder_snapshot'), 'movements', type_='check')
    op.drop_column('movements', 'destination_holder_display_name_snapshot')
    op.drop_column('movements', 'destination_holder_user_id')
    op.drop_column('movements', 'source_holder_user_id')
    op.drop_column('movements', 'comment')
    op.drop_column('movements', 'source_holder_display_name_snapshot')
    op.drop_column('movements', 'purpose')
    op.alter_column('stock_balances', 'location_id',
                   existing_type=sa.UUID(),
                   nullable=False)
    op.drop_index(op.f('ix_stock_balances_holder_user_id'), table_name='stock_balances')
    op.drop_index(op.f('ux_stock_balances_item_holder'), table_name='stock_balances', postgresql_where='(location_id IS NULL)')
    op.drop_index(op.f('ux_stock_balances_item_location'), table_name='stock_balances', postgresql_where='(holder_user_id IS NULL)')
    op.create_unique_constraint('uq_stock_balances_item_id_location_id', 'stock_balances', ['item_id', 'location_id'])
    op.drop_constraint(op.f('fk_stock_balances_holder_user_id_users'), 'stock_balances', type_='foreignkey')
    op.create_foreign_key(op.f('fk_stock_balances_item_id_items'), 'stock_balances', 'items', ['item_id'], ['id'], ondelete='RESTRICT')
    op.drop_constraint(op.f('ck_stock_balances_quantity_item_only'), 'stock_balances', type_='check')
    op.drop_constraint(op.f('ck_stock_balances_single_position'), 'stock_balances', type_='check')
    op.drop_column('stock_balances', 'item_accounting_mode')
    op.drop_column('stock_balances', 'holder_user_id')
    _new_constraints_and_configuration()


def downgrade() -> None:
    _guard_empty("downgrade")
    _drop_v2_triggers()
    op.execute("DELETE FROM category_attributes")
    op.execute("DELETE FROM categories WHERE parent_id IS NOT NULL")
    op.execute("DELETE FROM categories")
    op.drop_constraint(op.f("ck_movements_operation_positions"), "movements", type_="check")
    op.drop_constraint(op.f("ck_movements_positions_distinct"), "movements", type_="check")
    op.add_column('categories', sa.Column('default_accounting_mode', sa.VARCHAR(length=8), autoincrement=False, nullable=False))
    op.create_check_constraint(op.f('ck_categories_default_accounting_mode'), 'categories', "default_accounting_mode::text = ANY (ARRAY['QUANTITY'::character varying, 'SERIAL'::character varying]::text[])")
    op.drop_constraint(op.f('fk_categories_parent_id_categories'), 'categories', type_='foreignkey')
    op.drop_index(op.f('ix_categories_parent_id'), table_name='categories')
    op.drop_column('categories', 'parent_id')
    op.add_column('items', sa.Column('technical_data_source', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('items', sa.Column('internal_code', sa.VARCHAR(length=128), autoincrement=False, nullable=True))
    op.add_column('items', sa.Column('normalized_internal_code', sa.VARCHAR(length=128), autoincrement=False, nullable=True))
    op.add_column('items', sa.Column('description', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('items', sa.Column('comment', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('items', sa.Column('accounting_mode', sa.VARCHAR(length=8), autoincrement=False, nullable=False))
    op.add_column('items', sa.Column('normalized_manufacturer_part_number', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.add_column('items', sa.Column('manufacturer_part_number', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.add_column('items', sa.Column('datasheet_url', sa.VARCHAR(length=2048), autoincrement=False, nullable=True))
    op.create_check_constraint(op.f('ck_items_accounting_mode'), 'items', "accounting_mode::text = ANY (ARRAY['QUANTITY'::character varying, 'SERIAL'::character varying]::text[])")
    op.drop_constraint(op.f('uq_items_identity_signature'), 'items', type_='unique')
    op.create_unique_constraint(op.f('uq_items_normalized_internal_code'), 'items', ['normalized_internal_code'], postgresql_nulls_not_distinct=False)
    op.create_unique_constraint(op.f('uq_items_id_accounting_mode'), 'items', ['id', 'accounting_mode'], postgresql_nulls_not_distinct=False)
    op.create_index(op.f('ix_items_normalized_mpn_trgm'), 'items', ['normalized_manufacturer_part_number'], unique=False, postgresql_ops={'normalized_manufacturer_part_number': 'gin_trgm_ops'}, postgresql_using='gin')
    op.create_index(op.f('ix_items_normalized_internal_code_trgm'), 'items', ['normalized_internal_code'], unique=False, postgresql_ops={'normalized_internal_code': 'gin_trgm_ops'}, postgresql_using='gin')
    op.create_index(op.f('ix_items_duplicate_mpn'), 'items', ['category_id', 'manufacturer_id', 'normalized_manufacturer_part_number'], unique=False)
    op.drop_column('items', 'identity_signature')
    op.add_column('locations', sa.Column('description', sa.TEXT(), autoincrement=False, nullable=True))
    op.drop_constraint(op.f('ck_locations_location_type'), 'locations', type_='check')
    op.drop_column('locations', 'location_type')
    op.drop_column('locations', 'address')
    op.create_table('inventory_units',
        sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('item_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('item_accounting_mode', sa.VARCHAR(length=8), server_default=sa.text("'SERIAL'::character varying"), autoincrement=False, nullable=False),
        sa.Column('serial_number', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column('normalized_serial_number', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column('wwn', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
        sa.Column('normalized_wwn', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
        sa.Column('comment', sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column('state', sa.VARCHAR(length=11), autoincrement=False, nullable=False),
        sa.Column('current_location_id', sa.UUID(), autoincrement=False, nullable=True),
        sa.Column('current_holder_user_id', sa.UUID(), autoincrement=False, nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
        sa.CheckConstraint("btrim(normalized_serial_number::text) <> ''::text", name=op.f('ck_inventory_units_normalized_serial_number_not_blank')),
        sa.CheckConstraint("btrim(serial_number::text) <> ''::text", name=op.f('ck_inventory_units_serial_number_not_blank')),
        sa.CheckConstraint("item_accounting_mode::text = 'SERIAL'::text", name=op.f('ck_inventory_units_serial_item_only')),
        sa.CheckConstraint("normalized_wwn IS NULL OR btrim(normalized_wwn::text) <> ''::text", name=op.f('ck_inventory_units_normalized_wwn_not_blank')),
        sa.CheckConstraint("state::text = 'STORED'::text AND current_location_id IS NOT NULL AND current_holder_user_id IS NULL OR state::text = 'ISSUED'::text AND current_location_id IS NULL AND current_holder_user_id IS NOT NULL OR (state::text = ANY (ARRAY['WRITTEN_OFF'::character varying, 'VOIDED'::character varying]::text[])) AND current_location_id IS NULL AND current_holder_user_id IS NULL", name=op.f('ck_inventory_units_current_position')),
        sa.CheckConstraint("state::text = ANY (ARRAY['STORED'::character varying, 'ISSUED'::character varying, 'WRITTEN_OFF'::character varying, 'VOIDED'::character varying]::text[])", name=op.f('ck_inventory_units_state')),
        sa.CheckConstraint("wwn IS NULL OR btrim(wwn::text) <> ''::text", name=op.f('ck_inventory_units_wwn_not_blank')),
        sa.ForeignKeyConstraint(['current_holder_user_id'], ['users.id'], name=op.f('fk_inventory_units_current_holder_user_id_users'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['current_location_id'], ['locations.id'], name=op.f('fk_inventory_units_current_location_id_locations'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['item_id', 'item_accounting_mode'], ['items.id', 'items.accounting_mode'], name=op.f('fk_inventory_units_item_id_items'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory_units')),
        sa.UniqueConstraint('id', 'item_id', name=op.f('uq_inventory_units_id_item_id'), postgresql_include=[], postgresql_nulls_not_distinct=False),
        sa.UniqueConstraint('item_id', 'normalized_serial_number', name=op.f('uq_inventory_units_item_id_normalized_serial_number'), postgresql_include=[], postgresql_nulls_not_distinct=False),
        sa.UniqueConstraint('normalized_wwn', name=op.f('uq_inventory_units_normalized_wwn'), postgresql_include=[], postgresql_nulls_not_distinct=False)
        )
    op.create_index(op.f('ix_inventory_units_state'), 'inventory_units', ['state'], unique=False)
    op.create_index(op.f('ix_inventory_units_normalized_wwn_trgm'), 'inventory_units', ['normalized_wwn'], unique=False, postgresql_ops={'normalized_wwn': 'gin_trgm_ops'}, postgresql_using='gin')
    op.create_index(op.f('ix_inventory_units_normalized_serial_trgm'), 'inventory_units', ['normalized_serial_number'], unique=False, postgresql_ops={'normalized_serial_number': 'gin_trgm_ops'}, postgresql_using='gin')
    op.create_index(op.f('ix_inventory_units_item_state_location'), 'inventory_units', ['item_id', 'state', 'current_location_id'], unique=False)
    op.create_index(op.f('ix_inventory_units_current_location_id'), 'inventory_units', ['current_location_id'], unique=False)
    op.create_index(op.f('ix_inventory_units_current_holder_user_id'), 'inventory_units', ['current_holder_user_id'], unique=False)
    op.add_column('movements', sa.Column('purpose', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.add_column('movements', sa.Column('source_holder_display_name_snapshot', sa.VARCHAR(length=579), autoincrement=False, nullable=True))
    op.add_column('movements', sa.Column('comment', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('movements', sa.Column('source_holder_user_id', sa.UUID(), autoincrement=False, nullable=True))
    op.add_column('movements', sa.Column('destination_holder_user_id', sa.UUID(), autoincrement=False, nullable=True))
    op.add_column('movements', sa.Column('destination_holder_display_name_snapshot', sa.VARCHAR(length=579), autoincrement=False, nullable=True))
    op.create_check_constraint(op.f('ck_movements_source_holder_snapshot'), 'movements', '(source_holder_user_id IS NULL) = (source_holder_display_name_snapshot IS NULL)')
    op.create_check_constraint(op.f('ck_movements_position_side_exclusive'), 'movements', 'num_nonnulls(source_location_id, source_holder_user_id) <= 1 AND num_nonnulls(destination_location_id, destination_holder_user_id) <= 1')
    op.create_check_constraint(op.f('ck_movements_destination_holder_snapshot'), 'movements', '(destination_holder_user_id IS NULL) = (destination_holder_display_name_snapshot IS NULL)')
    op.create_foreign_key(op.f('fk_movements_source_holder_user_id_users'), 'movements', 'users', ['source_holder_user_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key(op.f('fk_movements_destination_holder_user_id_users'), 'movements', 'users', ['destination_holder_user_id'], ['id'], ondelete='RESTRICT')
    op.drop_index('ix_movements_actor_occurred', table_name='movements')
    op.create_index(op.f('ix_movements_source_holder_user_id'), 'movements', ['source_holder_user_id'], unique=False)
    op.create_index(op.f('ix_movements_destination_holder_user_id'), 'movements', ['destination_holder_user_id'], unique=False)
    op.add_column('movement_lines', sa.Column('wwn_snapshot', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.add_column('movement_lines', sa.Column('serial_number_snapshot', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.add_column('movement_lines', sa.Column('manufacturer_part_number_snapshot', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
    op.add_column('movement_lines', sa.Column('inventory_unit_id', sa.UUID(), autoincrement=False, nullable=True))
    op.add_column('movement_lines', sa.Column('item_accounting_mode', sa.VARCHAR(length=8), autoincrement=False, nullable=False))
    op.drop_constraint(op.f('ck_movement_lines_quantity_positive'), 'movement_lines', type_='check')
    op.create_check_constraint(op.f('ck_movement_lines_item_accounting_mode'), 'movement_lines', "item_accounting_mode::text = ANY (ARRAY['QUANTITY'::character varying, 'SERIAL'::character varying]::text[])")
    op.create_check_constraint(op.f('ck_movement_lines_accounting_shape'), 'movement_lines', "item_accounting_mode::text = 'QUANTITY'::text AND quantity IS NOT NULL AND quantity > 0 AND inventory_unit_id IS NULL AND serial_number_snapshot IS NULL AND wwn_snapshot IS NULL OR item_accounting_mode::text = 'SERIAL'::text AND quantity IS NULL AND inventory_unit_id IS NOT NULL AND serial_number_snapshot IS NOT NULL AND btrim(serial_number_snapshot::text) <> ''::text AND (wwn_snapshot IS NULL OR btrim(wwn_snapshot::text) <> ''::text)")
    op.drop_constraint(op.f('fk_movement_lines_item_id_items'), 'movement_lines', type_='foreignkey')
    op.drop_constraint('uq_movement_lines_movement_id_item_id', 'movement_lines', type_='unique')
    op.create_index(op.f('ux_movement_lines_quantity_item'), 'movement_lines', ['movement_id', 'item_id'], unique=True, postgresql_where="((item_accounting_mode)::text = 'QUANTITY'::text)")
    op.create_unique_constraint(op.f('uq_movement_lines_movement_id_inventory_unit_id'), 'movement_lines', ['movement_id', 'inventory_unit_id'], postgresql_nulls_not_distinct=False)
    op.create_index(op.f('ix_movement_lines_inventory_unit_id'), 'movement_lines', ['inventory_unit_id'], unique=False)
    op.alter_column('movement_lines', 'quantity',
                   existing_type=sa.BIGINT(),
                   nullable=True)
    op.add_column('stock_balances', sa.Column('holder_user_id', sa.UUID(), autoincrement=False, nullable=True))
    op.add_column('stock_balances', sa.Column('item_accounting_mode', sa.VARCHAR(length=8), server_default=sa.text("'QUANTITY'::character varying"), autoincrement=False, nullable=False))
    op.create_check_constraint(op.f('ck_stock_balances_single_position'), 'stock_balances', 'num_nonnulls(location_id, holder_user_id) = 1')
    op.create_check_constraint(op.f('ck_stock_balances_quantity_item_only'), 'stock_balances', "item_accounting_mode::text = 'QUANTITY'::text")
    op.drop_constraint(op.f('fk_stock_balances_item_id_items'), 'stock_balances', type_='foreignkey')
    op.create_foreign_key(op.f('fk_stock_balances_holder_user_id_users'), 'stock_balances', 'users', ['holder_user_id'], ['id'], ondelete='RESTRICT')
    op.drop_constraint('uq_stock_balances_item_id_location_id', 'stock_balances', type_='unique')
    op.create_index(op.f('ux_stock_balances_item_location'), 'stock_balances', ['item_id', 'location_id'], unique=True, postgresql_where='(holder_user_id IS NULL)')
    op.create_index(op.f('ux_stock_balances_item_holder'), 'stock_balances', ['item_id', 'holder_user_id'], unique=True, postgresql_where='(location_id IS NULL)')
    op.create_index(op.f('ix_stock_balances_holder_user_id'), 'stock_balances', ['holder_user_id'], unique=False)
    op.alter_column('stock_balances', 'location_id',
                   existing_type=sa.UUID(),
                   nullable=True)
    op.create_foreign_key(op.f('fk_stock_balances_item_id_items'), 'stock_balances', 'items', ['item_id', 'item_accounting_mode'], ['id', 'accounting_mode'], ondelete='RESTRICT')
    op.create_foreign_key(op.f('fk_movement_lines_item_id_items'), 'movement_lines', 'items', ['item_id', 'item_accounting_mode'], ['id', 'accounting_mode'], ondelete='RESTRICT')
    op.create_foreign_key(op.f('fk_movement_lines_inventory_unit_id_inventory_units'), 'movement_lines', 'inventory_units', ['inventory_unit_id', 'item_id'], ['id', 'item_id'], ondelete='RESTRICT')
    _restore_previous_configuration()


def _frozen(name: str) -> dict[str, Any]:
    return json.loads((Path(__file__).parents[1] / 'data' / f'b3c4d5e6f7a8_{name}.json').read_text())


def _guard_empty(operation: str) -> None:
    # Locks exclude concurrent writes until the migration transaction commits.
    op.execute('LOCK TABLE items, locations, movements, movement_lines, stock_balances, '
               'item_attribute_values, categories, category_attributes IN ACCESS EXCLUSIVE MODE')
    connection = op.get_bind()
    for table in ('items', 'locations', 'movements', 'movement_lines', 'stock_balances', 'item_attribute_values'):
        if connection.execute(sa.text(f'SELECT EXISTS (SELECT 1 FROM {table})')).scalar():
            raise RuntimeError(f'warehouse v2 {operation} refused: {table} contains data; explicit reviewed mapping/recovery required')


def _guard_upgrade() -> None:
    op.execute('LOCK TABLE inventory_units, movements, movement_lines, stock_balances, items IN ACCESS EXCLUSIVE MODE')
    connection = op.get_bind()
    checks = {
        'per-unit data': 'SELECT 1 FROM inventory_units',
        'holder balances': 'SELECT 1 FROM stock_balances WHERE holder_user_id IS NOT NULL',
        'holder journal': 'SELECT 1 FROM movements WHERE source_holder_user_id IS NOT NULL OR destination_holder_user_id IS NOT NULL',
        'serial catalog': "SELECT 1 FROM items WHERE accounting_mode = 'SERIAL'",
        'serial history': "SELECT 1 FROM movement_lines WHERE inventory_unit_id IS NOT NULL OR serial_number_snapshot IS NOT NULL OR wwn_snapshot IS NOT NULL",
    }
    for label, query in checks.items():
        if connection.execute(sa.text(f'SELECT EXISTS ({query})')).scalar():
            raise RuntimeError(f'warehouse v2 refused: incompatible legacy {label}; no data was discarded')
    _guard_empty('upgrade')
    if connection.execute(sa.text('SELECT EXISTS (SELECT 1 FROM categories WHERE NOT is_system)')).scalar():
        raise RuntimeError('warehouse v2 refused: custom categories require explicit mapping')


def _new_constraints_and_configuration() -> None:
    op.create_check_constraint(op.f('ck_movements_positions_distinct'), 'movements',
        'source_location_id IS NULL OR destination_location_id IS NULL OR source_location_id <> destination_location_id')
    op.create_check_constraint(op.f('ck_movements_operation_positions'), 'movements',
        "(movement_type IN ('RECEIPT', 'RETURN') AND source_location_id IS NULL AND destination_location_id IS NOT NULL) OR "
        "(movement_type IN ('ISSUE', 'WRITE_OFF') AND source_location_id IS NOT NULL AND destination_location_id IS NULL) OR "
        "(movement_type = 'TRANSFER' AND source_location_id IS NOT NULL AND destination_location_id IS NOT NULL) OR "
        "(movement_type IN ('CORRECTION', 'REVERSAL') AND num_nonnulls(source_location_id, destination_location_id) BETWEEN 1 AND 2)")
    configuration = _frozen('configuration')
    connection = op.get_bind()
    ids = {key: str(uuid5(NAMESPACE_URL, 'spikatel:category:' + key))
           for key in [*configuration['families'], *configuration['leaves']]}
    for index, (key, (name, description)) in enumerate(configuration['families'].items()):
        connection.execute(sa.text('INSERT INTO categories (id,key,display_name,description,sort_order,is_system) '
                                   'VALUES (:id,:key,:name,:description,:sort,true)'),
                           dict(id=ids[key], key=key, name=name, description=description, sort=index))
    for index, (key, (parent, name, attributes)) in enumerate(configuration['leaves'].items()):
        connection.execute(sa.text('INSERT INTO categories (id,key,display_name,parent_id,sort_order,is_system) '
                                   'VALUES (:id,:key,:name,:parent,:sort,true)'),
                           dict(id=ids[key], key=key, name=name, parent=ids[parent], sort=index))
        for order, attribute in enumerate(attributes):
            numeric = attribute['data_type'] in ('INTEGER', 'DECIMAL')
            metadata = {'min': 1 if attribute['data_type'] == 'INTEGER' else 0.0000000001} if numeric else {'max_length': 2000} if attribute['data_type'] == 'TEXT' else None
            connection.execute(sa.text('''INSERT INTO category_attributes
                (id,category_id,key,label,data_type,unit,required,filterable,searchable,card_visible,
                 detail_visible,table_visible,excel_visible,sort_order,filter_type,validation_metadata,is_system)
                VALUES (:id,:category,:key,:label,:type,:unit,:required,true,true,:visible,:visible,true,true,
                        :sort,:filter,CAST(:metadata AS jsonb),true)'''),
                dict(id=str(uuid5(NAMESPACE_URL, 'spikatel:attribute:' + key + ':' + attribute['key'])),
                     category=ids[key], key=attribute['key'], label=attribute['label'],
                     type=attribute['data_type'], unit=attribute['unit'], required=attribute['required'],
                     visible=not attribute['derived'], sort=order, filter='RANGE' if numeric else 'EXACT',
                     metadata=json.dumps(metadata) if metadata is not None else None))
    op.execute('''CREATE FUNCTION validate_v2_category() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.parent_id IS NOT NULL AND (NEW.parent_id = NEW.id OR NOT EXISTS
                (SELECT 1 FROM categories WHERE id = NEW.parent_id AND parent_id IS NULL)) THEN
                RAISE EXCEPTION 'category parent must be a top-level family' USING ERRCODE='23514';
            END IF;
            IF TG_OP = 'UPDATE' AND (NEW.parent_id IS DISTINCT FROM OLD.parent_id OR NEW.key <> OLD.key) THEN
                RAISE EXCEPTION 'category hierarchy is fixed product configuration' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$''')
    op.execute('CREATE TRIGGER trg_categories_hierarchy BEFORE INSERT OR UPDATE ON categories FOR EACH ROW EXECUTE FUNCTION validate_v2_category()')
    op.execute('''CREATE FUNCTION validate_v2_leaf() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM categories WHERE id=NEW.category_id AND parent_id IS NOT NULL) THEN
                RAISE EXCEPTION 'item/attribute requires a leaf category' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$''')
    for table in ('items', 'category_attributes'):
        op.execute(f'CREATE TRIGGER trg_{table}_leaf BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION validate_v2_leaf()')
    op.execute('''CREATE OR REPLACE FUNCTION validate_warehouse_correction_header()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE original movements%ROWTYPE;
        BEGIN
            IF NEW.movement_type NOT IN ('CORRECTION', 'REVERSAL') THEN RETURN NEW; END IF;
            SELECT * INTO original FROM movements WHERE id=NEW.original_movement_id;
            IF NOT FOUND OR original.movement_type='REVERSAL' THEN
                RAISE EXCEPTION 'invalid correction/reversal target' USING ERRCODE='23514';
            END IF;
            IF NEW.movement_type='REVERSAL' THEN
                IF NEW.line_count <> original.line_count THEN
                    RAISE EXCEPTION 'reversal must include every original line' USING ERRCODE='23514';
                END IF;
                IF NEW.source_location_id IS DISTINCT FROM original.destination_location_id
                   OR NEW.destination_location_id IS DISTINCT FROM original.source_location_id THEN
                    RAISE EXCEPTION 'reversal must invert original locations' USING ERRCODE='23514';
                END IF;
            ELSIF NOT coalesce(NEW.source_location_id IN (original.source_location_id, original.destination_location_id)
                  OR NEW.destination_location_id IN (original.source_location_id, original.destination_location_id), false) THEN
                RAISE EXCEPTION 'correction must concern original location' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$''')
    op.execute('''CREATE OR REPLACE FUNCTION validate_warehouse_correction_line()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE header movements%ROWTYPE;
        BEGIN
            SELECT * INTO header FROM movements WHERE id=NEW.movement_id;
            IF header.movement_type IN ('CORRECTION','REVERSAL') AND NOT EXISTS
                (SELECT 1 FROM movement_lines WHERE movement_id=header.original_movement_id
                 AND item_id=NEW.item_id AND (header.movement_type='CORRECTION' OR quantity=NEW.quantity)) THEN
                RAISE EXCEPTION 'invalid original item/quantity relationship' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$''')


def _drop_v2_triggers() -> None:
    for table, trigger in (('items','trg_items_leaf'), ('category_attributes','trg_category_attributes_leaf'),
                           ('categories','trg_categories_hierarchy')):
        op.execute(f'DROP TRIGGER {trigger} ON {table}')
    op.execute('DROP FUNCTION validate_v2_leaf()')
    op.execute('DROP FUNCTION validate_v2_category()')


def _restore_previous_configuration() -> None:
    previous = _frozen('previous_configuration')
    connection = op.get_bind()
    for table in ('categories', 'category_attributes'):
        connection.execute(sa.text(f'INSERT INTO {table} SELECT * FROM json_populate_recordset(NULL::{table}, :rows)'),
                           {'rows': json.dumps(previous[table])})
    for definition in previous['functions'].values():
        op.execute(definition)
    # Old expressions are frozen in the original configuration snapshot below.
    op.create_check_constraint(op.f('ck_movements_positions_distinct'), 'movements',
        'NOT (source_location_id IS NOT NULL AND source_location_id = destination_location_id) '
        'AND NOT (source_holder_user_id IS NOT NULL AND source_holder_user_id = destination_holder_user_id)')
    op.create_check_constraint(op.f('ck_movements_operation_positions'), 'movements', PREVIOUS_POSITIONS)


PREVIOUS_POSITIONS = """
(movement_type = 'RECEIPT' AND source_location_id IS NULL AND source_holder_user_id IS NULL
 AND destination_location_id IS NOT NULL AND destination_holder_user_id IS NULL)
OR (movement_type = 'ISSUE' AND source_location_id IS NOT NULL AND source_holder_user_id IS NULL
 AND destination_location_id IS NULL AND destination_holder_user_id IS NOT NULL)
OR (movement_type = 'RETURN' AND source_location_id IS NULL AND source_holder_user_id IS NOT NULL
 AND destination_location_id IS NOT NULL AND destination_holder_user_id IS NULL)
OR (movement_type = 'TRANSFER' AND source_location_id IS NOT NULL AND source_holder_user_id IS NULL
 AND destination_location_id IS NOT NULL AND destination_holder_user_id IS NULL)
OR (movement_type = 'WRITE_OFF' AND num_nonnulls(source_location_id, source_holder_user_id) = 1
 AND destination_location_id IS NULL AND destination_holder_user_id IS NULL)
OR (movement_type IN ('CORRECTION', 'REVERSAL') AND num_nonnulls(source_location_id,
 source_holder_user_id, destination_location_id, destination_holder_user_id) BETWEEN 1 AND 2)
"""
