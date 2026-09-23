"""Harden Catalog derived identity invariants.

Revision ID: f8b9c0d1e2f3
Revises: f7a8b9c0d1e2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8b9c0d1e2f3"
down_revision: str | Sequence[str] | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE COLLATION public.dc_inventory_unicode_fast
        (
            provider = builtin,
            locale = 'PG_UNICODE_FAST'
        )
        """
    )

    op.execute(
        """
        CREATE FUNCTION catalog_normalize_comparison(value text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        AS $$
            SELECT casefold(
                btrim(
                    regexp_replace(
                        value
                            COLLATE public.dc_inventory_unicode_fast,
                        '[[:space:]]+',
                        ' ',
                        'g'
                    )
                )
                COLLATE public.dc_inventory_unicode_fast
            )
        $$
        """
    )

    op.execute(
        """
        CREATE FUNCTION catalog_identity_text(value text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        AS $$
            SELECT casefold(
                btrim(
                    regexp_replace(
                        normalize(value, NFKC)
                            COLLATE public.dc_inventory_unicode_fast,
                        '[[:space:]]+',
                        ' ',
                        'g'
                    )
                )
                COLLATE public.dc_inventory_unicode_fast
            )
        $$
        """
    )

    op.execute(
        """
        CREATE FUNCTION catalog_decimal_identity(value numeric)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE
        STRICT
        PARALLEL SAFE
        AS $$
            SELECT trim_scale(value)::text
        $$
        """
    )

    op.execute(
        """
        CREATE FUNCTION catalog_item_signature(
            target_item_id uuid
        )
        RETURNS text
        LANGUAGE sql
        STABLE
        AS $$
            WITH item_data AS (
                SELECT
                    i.id,
                    c.key AS category_key,
                    m.name AS manufacturer_name,
                    i.model
                FROM items i
                JOIN categories c
                  ON c.id = i.category_id
                LEFT JOIN manufacturers m
                  ON m.id = i.manufacturer_id
                WHERE i.id = target_item_id
            ),
            attribute_data AS (
                SELECT
                    iav.item_id,
                    string_agg(
                        to_json(ca.key)::text
                        || ':'
                        || CASE
                            WHEN iav.text_value IS NOT NULL
                                THEN to_json(
                                    catalog_identity_text(
                                        iav.text_value
                                    )
                                )::text
                            WHEN iav.integer_value IS NOT NULL
                                THEN iav.integer_value::text
                            WHEN iav.decimal_value IS NOT NULL
                                THEN to_json(
                                    catalog_decimal_identity(
                                        iav.decimal_value
                                    )
                                )::text
                            WHEN iav.boolean_value IS NOT NULL
                                THEN CASE
                                    WHEN iav.boolean_value
                                        THEN 'true'
                                    ELSE 'false'
                                END
                            WHEN iav.enum_value IS NOT NULL
                                THEN to_json(
                                    catalog_identity_text(
                                        iav.enum_value
                                    )
                                )::text
                            ELSE 'null'
                        END,
                        ','
                        ORDER BY ca.key COLLATE "C"
                    ) AS attributes_json
                FROM item_attribute_values iav
                JOIN category_attributes ca
                  ON ca.id = iav.category_attribute_id
                WHERE iav.item_id = target_item_id
                GROUP BY iav.item_id
            )
            SELECT encode(
                sha256(
                    convert_to(
                        '['
                        || to_json(d.category_key)::text
                        || ','
                        || to_json(
                            catalog_identity_text(
                                coalesce(
                                    d.manufacturer_name,
                                    ''
                                )
                            )
                        )::text
                        || ','
                        || to_json(
                            catalog_identity_text(
                                coalesce(d.model, '')
                            )
                        )::text
                        || ',{'
                        || coalesce(
                            a.attributes_json,
                            ''
                        )
                        || '}]',
                        'UTF8'
                    )
                ),
                'hex'
            )
            FROM item_data d
            LEFT JOIN attribute_data a
              ON a.item_id = d.id
        $$
        """
    )

    connection = op.get_bind()

    duplicate_signatures = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT
                    catalog_item_signature(i.id)
                        AS expected_signature
                FROM items i
                GROUP BY
                    catalog_item_signature(i.id)
                HAVING count(*) > 1
            ) duplicates
            """
        )
    ).scalar_one()

    if duplicate_signatures:
        raise RuntimeError(
            "catalog identity invariant cannot be enabled: "
            f"{duplicate_signatures} canonical duplicate "
            "signature groups exist"
        )

    # normalized_* and identity_signature are derived state.
    # Reconcile them once before enabling fail-closed validation.
    op.execute(
        """
        UPDATE items
        SET
            normalized_name =
                catalog_normalize_comparison(name),
            normalized_model =
                CASE
                    WHEN model IS NULL
                        THEN NULL
                    ELSE catalog_normalize_comparison(model)
                END
        """
    )

    op.execute(
        """
        UPDATE items
        SET identity_signature =
            catalog_item_signature(id)
        """
    )

    op.execute(
        """
        CREATE FUNCTION assert_catalog_item_identity(
            target_item_id uuid
        )
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        DECLARE
            item_name text;
            item_normalized_name text;
            item_model text;
            item_normalized_model text;
            item_signature text;
            expected_normalized_name text;
            expected_normalized_model text;
            expected_signature text;
        BEGIN
            SELECT
                name,
                normalized_name,
                model,
                normalized_model,
                identity_signature
            INTO
                item_name,
                item_normalized_name,
                item_model,
                item_normalized_model,
                item_signature
            FROM items
            WHERE id = target_item_id;

            IF NOT FOUND THEN
                RETURN;
            END IF;

            expected_normalized_name :=
                catalog_normalize_comparison(
                    item_name
                );

            expected_normalized_model :=
                CASE
                    WHEN item_model IS NULL
                        THEN NULL
                    ELSE catalog_normalize_comparison(
                        item_model
                    )
                END;

            expected_signature :=
                catalog_item_signature(
                    target_item_id
                );

            IF item_normalized_name
                IS DISTINCT FROM expected_normalized_name
            THEN
                RAISE EXCEPTION
                    'items.normalized_name diverges '
                    'from canonical name'
                    USING ERRCODE = '23514';
            END IF;

            IF item_normalized_model
                IS DISTINCT FROM expected_normalized_model
            THEN
                RAISE EXCEPTION
                    'items.normalized_model diverges '
                    'from canonical model'
                    USING ERRCODE = '23514';
            END IF;

            IF item_signature
                IS DISTINCT FROM expected_signature
            THEN
                RAISE EXCEPTION
                    'items.identity_signature diverges '
                    'from canonical Item/EAV identity'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$
        """
    )

    # The BEFORE locks serialize Item and EAV identity mutations on one
    # logical catalog item. Deferred validators then observe the completed
    # transaction shape, preserving normal delete+reinsert EAV updates.
    op.execute(
        """
        CREATE FUNCTION lock_catalog_item_identity()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            PERFORM pg_advisory_xact_lock(
                hashtextextended(
                    NEW.id::text,
                    61505
                )
            );

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_items_lock_identity
        BEFORE INSERT OR UPDATE ON items
        FOR EACH ROW
        EXECUTE FUNCTION lock_catalog_item_identity()
        """
    )

    op.execute(
        """
        CREATE FUNCTION lock_catalog_item_attribute_identity()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            first_item_id uuid;
            second_item_id uuid;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                first_item_id := OLD.item_id;

            ELSIF TG_OP = 'UPDATE'
                AND OLD.item_id
                    IS DISTINCT FROM NEW.item_id
            THEN
                IF OLD.item_id::text < NEW.item_id::text THEN
                    first_item_id := OLD.item_id;
                    second_item_id := NEW.item_id;
                ELSE
                    first_item_id := NEW.item_id;
                    second_item_id := OLD.item_id;
                END IF;

            ELSE
                first_item_id := NEW.item_id;
            END IF;

            PERFORM pg_advisory_xact_lock(
                hashtextextended(
                    first_item_id::text,
                    61505
                )
            );

            IF second_item_id IS NOT NULL THEN
                PERFORM pg_advisory_xact_lock(
                    hashtextextended(
                        second_item_id::text,
                        61505
                    )
                );
            END IF;

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TRIGGER
            trg_item_attribute_values_lock_identity
        BEFORE INSERT OR UPDATE OR DELETE
        ON item_attribute_values
        FOR EACH ROW
        EXECUTE FUNCTION
            lock_catalog_item_attribute_identity()
        """
    )

    op.execute(
        """
        CREATE FUNCTION validate_catalog_item_identity()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            PERFORM assert_catalog_item_identity(
                NEW.id
            );

            RETURN NULL;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
            trg_items_validate_identity
        AFTER INSERT OR UPDATE ON items
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION
            validate_catalog_item_identity()
        """
    )

    op.execute(
        """
        CREATE FUNCTION
            validate_catalog_item_attribute_identity()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                PERFORM assert_catalog_item_identity(
                    OLD.item_id
                );

            ELSIF TG_OP = 'UPDATE'
                AND OLD.item_id
                    IS DISTINCT FROM NEW.item_id
            THEN
                PERFORM assert_catalog_item_identity(
                    OLD.item_id
                );

                PERFORM assert_catalog_item_identity(
                    NEW.item_id
                );

            ELSE
                PERFORM assert_catalog_item_identity(
                    NEW.item_id
                );
            END IF;

            RETURN NULL;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
            trg_item_attribute_values_validate_identity
        AFTER INSERT OR UPDATE OR DELETE
        ON item_attribute_values
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION
            validate_catalog_item_attribute_identity()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_item_attribute_values_validate_identity
        ON item_attribute_values
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS
            validate_catalog_item_attribute_identity()
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_items_validate_identity
        ON items
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS
            validate_catalog_item_identity()
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_item_attribute_values_lock_identity
        ON item_attribute_values
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS
            lock_catalog_item_attribute_identity()
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_items_lock_identity
        ON items
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS
            lock_catalog_item_identity()
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS
            assert_catalog_item_identity(uuid)
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS
            catalog_item_signature(uuid)
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS
            catalog_decimal_identity(numeric)
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS
            catalog_identity_text(text)
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS
            catalog_normalize_comparison(text)
        """
    )

    op.execute(
        """
        DROP COLLATION IF EXISTS
            public.dc_inventory_unicode_fast
        """
    )
