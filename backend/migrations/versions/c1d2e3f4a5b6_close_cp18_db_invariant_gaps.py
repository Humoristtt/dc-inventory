"""Close CP-18 Procurement and Catalog database invariant gaps.

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "b0c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROCUREMENT_STATUSES = (
    "AGREEMENT_PENDING_MANAGER",
    "AGREEMENT_REVISION_REQUIRED",
    "PURCHASING",
    "AWAITING_ACCEPTANCE",
    "COMPLETED",
)


def _status_check(column: str) -> str:
    values = ", ".join(f"'{value}'" for value in PROCUREMENT_STATUSES)
    return f"{column} IS NULL OR {column} IN ({values})"


def upgrade() -> None:
    connection = op.get_bind()

    invalid_typed_values = connection.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM item_attribute_values iav
                JOIN category_attributes ca
                  ON ca.id = iav.category_attribute_id
                 AND ca.category_id = iav.category_id
                WHERE CASE ca.data_type
                    WHEN 'TEXT' THEN iav.text_value IS NULL
                    WHEN 'INTEGER' THEN iav.integer_value IS NULL
                    WHEN 'DECIMAL' THEN iav.decimal_value IS NULL
                    WHEN 'BOOLEAN' THEN iav.boolean_value IS NULL
                    WHEN 'ENUM' THEN iav.enum_value IS NULL
                    ELSE true
                END
            )
            """
        )
    )
    if invalid_typed_values:
        raise RuntimeError(
            "item_attribute_values contain values that do not match "
            "category_attributes.data_type"
        )

    cross_request_events = connection.scalar(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM procurement_events pe
                JOIN procurement_revisions pr
                  ON pr.id = pe.revision_id
                WHERE pe.revision_id IS NOT NULL
                  AND pr.request_id <> pe.request_id
            )
            """
        )
    )
    if cross_request_events:
        raise RuntimeError(
            "procurement_events contain revisions from another request"
        )

    op.create_check_constraint(
        op.f("ck_procurement_events_from_status"),
        "procurement_events",
        _status_check("from_status"),
    )
    op.create_check_constraint(
        op.f("ck_procurement_events_to_status"),
        "procurement_events",
        _status_check("to_status"),
    )

    op.drop_constraint(
        op.f(
            "fk_procurement_events_revision_id_procurement_revisions"
        ),
        "procurement_events",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f(
            "fk_procurement_events_revision_id_request_id_"
            "procurement_revisions"
        ),
        "procurement_events",
        "procurement_revisions",
        ["revision_id", "request_id"],
        ["id", "request_id"],
        ondelete="RESTRICT",
    )

    op.execute(
        """
        CREATE FUNCTION validate_item_attribute_value_data_type()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            expected_data_type text;
        BEGIN
            SELECT data_type
            INTO expected_data_type
            FROM category_attributes
            WHERE id = NEW.category_attribute_id
              AND category_id = NEW.category_id;

            IF NOT FOUND THEN
                RETURN NEW;
            END IF;

            IF (
                expected_data_type = 'TEXT'
                AND NEW.text_value IS NULL
            ) OR (
                expected_data_type = 'INTEGER'
                AND NEW.integer_value IS NULL
            ) OR (
                expected_data_type = 'DECIMAL'
                AND NEW.decimal_value IS NULL
            ) OR (
                expected_data_type = 'BOOLEAN'
                AND NEW.boolean_value IS NULL
            ) OR (
                expected_data_type = 'ENUM'
                AND NEW.enum_value IS NULL
            ) THEN
                RAISE EXCEPTION
                    'item attribute value does not match declared data type'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_item_attribute_values_validate_data_type
        BEFORE INSERT OR UPDATE OF
            category_attribute_id,
            category_id,
            text_value,
            integer_value,
            decimal_value,
            boolean_value,
            enum_value
        ON item_attribute_values
        FOR EACH ROW
        EXECUTE FUNCTION validate_item_attribute_value_data_type()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_procurement_final_movement_binding()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'UPDATE'
               AND OLD.status = 'COMPLETED'
               AND (
                   NEW.status IS DISTINCT FROM OLD.status
                   OR NEW.final_movement_id
                      IS DISTINCT FROM OLD.final_movement_id
                   OR NEW.completed_at
                      IS DISTINCT FROM OLD.completed_at
               ) THEN
                RAISE EXCEPTION
                    'completed procurement receipt binding is immutable'
                    USING ERRCODE = '23514';
            END IF;

            IF NEW.final_movement_id IS NOT NULL
               AND (
                   TG_OP = 'INSERT'
                   OR OLD.final_movement_id
                      IS DISTINCT FROM NEW.final_movement_id
               ) THEN
                PERFORM pg_advisory_xact_lock(
                    hashtextextended(
                        NEW.final_movement_id::text,
                        61502
                    )
                );

                IF EXISTS (
                    SELECT 1
                    FROM movements
                    WHERE original_movement_id
                          = NEW.final_movement_id
                      AND movement_type IN (
                          'CORRECTION',
                          'REVERSAL'
                      )
                ) THEN
                    RAISE EXCEPTION
                        'adjusted movement cannot become procurement receipt'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_procurement_final_movement_binding()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.final_movement_id IS NOT NULL
               AND (
                   TG_OP = 'INSERT'
                   OR OLD.final_movement_id
                      IS DISTINCT FROM NEW.final_movement_id
               ) THEN
                PERFORM pg_advisory_xact_lock(
                    hashtextextended(
                        NEW.final_movement_id::text,
                        61502
                    )
                );

                IF EXISTS (
                    SELECT 1
                    FROM movements
                    WHERE original_movement_id
                          = NEW.final_movement_id
                      AND movement_type IN (
                          'CORRECTION',
                          'REVERSAL'
                      )
                ) THEN
                    RAISE EXCEPTION
                        'adjusted movement cannot become procurement receipt'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_item_attribute_values_validate_data_type
        ON item_attribute_values
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            validate_item_attribute_value_data_type()
        """
    )

    op.drop_constraint(
        op.f(
            "fk_procurement_events_revision_id_request_id_"
            "procurement_revisions"
        ),
        "procurement_events",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f(
            "fk_procurement_events_revision_id_procurement_revisions"
        ),
        "procurement_events",
        "procurement_revisions",
        ["revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        op.f("ck_procurement_events_to_status"),
        "procurement_events",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_procurement_events_from_status"),
        "procurement_events",
        type_="check",
    )
