"""Enforce journal-controlled warehouse projections.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: str | Sequence[str] | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAX_SAFE_QUANTITY = 2**53 - 1


def _projection_drift_exists() -> bool:
    connection = op.get_bind()
    return bool(
        connection.scalar(
            sa.text(
                """
                WITH stock_deltas AS (
                    SELECT
                        ml.item_id,
                        m.source_location_id AS location_id,
                        -ml.quantity AS delta
                    FROM movement_lines ml
                    JOIN movements m ON m.id = ml.movement_id
                    WHERE m.source_location_id IS NOT NULL

                    UNION ALL

                    SELECT
                        ml.item_id,
                        m.destination_location_id AS location_id,
                        ml.quantity AS delta
                    FROM movement_lines ml
                    JOIN movements m ON m.id = ml.movement_id
                    WHERE m.destination_location_id IS NOT NULL
                ),
                expected_stock AS (
                    SELECT
                        item_id,
                        location_id,
                        sum(delta) AS quantity
                    FROM stock_deltas
                    GROUP BY item_id, location_id
                    HAVING sum(delta) <> 0
                ),
                stock_drift AS (
                    SELECT 1
                    FROM expected_stock expected
                    FULL JOIN stock_balances actual
                      USING (item_id, location_id)
                    WHERE coalesce(expected.quantity, 0)
                          <> coalesce(actual.quantity, 0)
                ),
                custody_deltas AS (
                    SELECT
                        ml.item_id,
                        m.custody_user_id AS user_id,
                        CASE
                            WHEN m.movement_type = 'ISSUE'
                                THEN ml.quantity
                            WHEN m.movement_type = 'RETURN'
                                THEN -ml.quantity
                            WHEN m.movement_type = 'REVERSAL'
                                 AND original.movement_type = 'ISSUE'
                                THEN -ml.quantity
                            WHEN m.movement_type = 'REVERSAL'
                                 AND original.movement_type = 'RETURN'
                                THEN ml.quantity
                            ELSE 0
                        END AS delta
                    FROM movement_lines ml
                    JOIN movements m ON m.id = ml.movement_id
                    LEFT JOIN movements original
                      ON original.id = m.original_movement_id
                    WHERE m.custody_user_id IS NOT NULL
                ),
                expected_custody AS (
                    SELECT
                        item_id,
                        user_id,
                        sum(delta) AS quantity
                    FROM custody_deltas
                    GROUP BY item_id, user_id
                    HAVING sum(delta) <> 0
                ),
                custody_drift AS (
                    SELECT 1
                    FROM expected_custody expected
                    FULL JOIN user_item_custody_balances actual
                      USING (item_id, user_id)
                    WHERE coalesce(expected.quantity, 0)
                          <> coalesce(actual.quantity, 0)
                )
                SELECT
                    EXISTS (SELECT 1 FROM stock_drift)
                    OR EXISTS (SELECT 1 FROM custody_drift)
                """
            )
        )
    )


def upgrade() -> None:
    if _projection_drift_exists():
        raise RuntimeError(
            "warehouse projection drift exists; "
            "reconcile/recover before enabling journal-controlled writes"
        )

    op.execute(
        f"""
        CREATE FUNCTION refresh_warehouse_projection(
            p_movement_id uuid,
            p_item_id uuid
        )
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $projection$
        DECLARE
            header public.movements%ROWTYPE;
            expected_quantity numeric;
            expected_custody numeric;
        BEGIN
            SELECT *
            INTO header
            FROM public.movements
            WHERE id = p_movement_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'warehouse projection refresh requires an existing movement'
                    USING ERRCODE = '23503';
            END IF;

            PERFORM 1
            FROM public.movement_lines
            WHERE movement_id = p_movement_id
              AND item_id = p_item_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION
                    'warehouse projection refresh requires an existing movement line'
                    USING ERRCODE = '23503';
            END IF;

            IF header.source_location_id IS NOT NULL THEN
                SELECT coalesce(
                    sum(
                        CASE
                            WHEN m.destination_location_id
                                 = header.source_location_id
                                THEN ml.quantity
                            ELSE 0
                        END
                        -
                        CASE
                            WHEN m.source_location_id
                                 = header.source_location_id
                                THEN ml.quantity
                            ELSE 0
                        END
                    ),
                    0
                )
                INTO expected_quantity
                FROM public.movement_lines ml
                JOIN public.movements m
                  ON m.id = ml.movement_id
                WHERE ml.item_id = p_item_id
                  AND (
                      m.source_location_id = header.source_location_id
                      OR m.destination_location_id
                         = header.source_location_id
                  );

                IF expected_quantity < 0
                   OR expected_quantity > {MAX_SAFE_QUANTITY} THEN
                    RAISE EXCEPTION
                        'warehouse stock projection is outside supported range'
                        USING ERRCODE = '23514';
                END IF;

                IF expected_quantity = 0 THEN
                    DELETE FROM public.stock_balances
                    WHERE item_id = p_item_id
                      AND location_id = header.source_location_id;
                ELSE
                    INSERT INTO public.stock_balances (
                        id,
                        item_id,
                        location_id,
                        quantity
                    )
                    VALUES (
                        gen_random_uuid(),
                        p_item_id,
                        header.source_location_id,
                        expected_quantity::bigint
                    )
                    ON CONFLICT (item_id, location_id)
                    DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        updated_at = now();
                END IF;
            END IF;

            IF header.destination_location_id IS NOT NULL
               AND header.destination_location_id
                   IS DISTINCT FROM header.source_location_id THEN
                SELECT coalesce(
                    sum(
                        CASE
                            WHEN m.destination_location_id
                                 = header.destination_location_id
                                THEN ml.quantity
                            ELSE 0
                        END
                        -
                        CASE
                            WHEN m.source_location_id
                                 = header.destination_location_id
                                THEN ml.quantity
                            ELSE 0
                        END
                    ),
                    0
                )
                INTO expected_quantity
                FROM public.movement_lines ml
                JOIN public.movements m
                  ON m.id = ml.movement_id
                WHERE ml.item_id = p_item_id
                  AND (
                      m.source_location_id
                          = header.destination_location_id
                      OR m.destination_location_id
                          = header.destination_location_id
                  );

                IF expected_quantity < 0
                   OR expected_quantity > {MAX_SAFE_QUANTITY} THEN
                    RAISE EXCEPTION
                        'warehouse stock projection is outside supported range'
                        USING ERRCODE = '23514';
                END IF;

                IF expected_quantity = 0 THEN
                    DELETE FROM public.stock_balances
                    WHERE item_id = p_item_id
                      AND location_id = header.destination_location_id;
                ELSE
                    INSERT INTO public.stock_balances (
                        id,
                        item_id,
                        location_id,
                        quantity
                    )
                    VALUES (
                        gen_random_uuid(),
                        p_item_id,
                        header.destination_location_id,
                        expected_quantity::bigint
                    )
                    ON CONFLICT (item_id, location_id)
                    DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        updated_at = now();
                END IF;
            END IF;

            IF header.custody_user_id IS NOT NULL THEN
                SELECT coalesce(
                    sum(
                        CASE
                            WHEN m.movement_type = 'ISSUE'
                                THEN ml.quantity
                            WHEN m.movement_type = 'RETURN'
                                THEN -ml.quantity
                            WHEN m.movement_type = 'REVERSAL'
                                 AND original.movement_type = 'ISSUE'
                                THEN -ml.quantity
                            WHEN m.movement_type = 'REVERSAL'
                                 AND original.movement_type = 'RETURN'
                                THEN ml.quantity
                            ELSE 0
                        END
                    ),
                    0
                )
                INTO expected_custody
                FROM public.movement_lines ml
                JOIN public.movements m
                  ON m.id = ml.movement_id
                LEFT JOIN public.movements original
                  ON original.id = m.original_movement_id
                WHERE ml.item_id = p_item_id
                  AND m.custody_user_id = header.custody_user_id;

                IF expected_custody < 0
                   OR expected_custody > {MAX_SAFE_QUANTITY} THEN
                    RAISE EXCEPTION
                        'warehouse custody projection is outside supported range'
                        USING ERRCODE = '23514';
                END IF;

                IF expected_custody = 0 THEN
                    DELETE FROM public.user_item_custody_balances
                    WHERE user_id = header.custody_user_id
                      AND item_id = p_item_id;
                ELSE
                    INSERT INTO public.user_item_custody_balances (
                        id,
                        user_id,
                        item_id,
                        quantity
                    )
                    VALUES (
                        gen_random_uuid(),
                        header.custody_user_id,
                        p_item_id,
                        expected_custody::bigint
                    )
                    ON CONFLICT (user_id, item_id)
                    DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        updated_at = now();
                END IF;
            END IF;
        END;
        $projection$
        """
    )

    op.execute(
        """
        REVOKE ALL
        ON FUNCTION refresh_warehouse_projection(uuid, uuid)
        FROM PUBLIC
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            refresh_warehouse_projection(uuid, uuid)
        """
    )
