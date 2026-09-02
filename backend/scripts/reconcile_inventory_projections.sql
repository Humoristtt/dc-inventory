-- Read-only Stage 6 projection reconciliation.
-- A healthy database returns zero rows from both result sets.

WITH journal_delta AS (
    SELECT
        ml.item_id,
        m.source_location_id AS location_id,
        m.source_holder_user_id AS holder_user_id,
        -ml.quantity AS quantity_delta
    FROM movement_lines AS ml
    JOIN movements AS m ON m.id = ml.movement_id
    WHERE ml.item_accounting_mode = 'QUANTITY'
      AND (m.source_location_id IS NOT NULL OR m.source_holder_user_id IS NOT NULL)
    UNION ALL
    SELECT
        ml.item_id,
        m.destination_location_id AS location_id,
        m.destination_holder_user_id AS holder_user_id,
        ml.quantity AS quantity_delta
    FROM movement_lines AS ml
    JOIN movements AS m ON m.id = ml.movement_id
    WHERE ml.item_accounting_mode = 'QUANTITY'
      AND (
          m.destination_location_id IS NOT NULL
          OR m.destination_holder_user_id IS NOT NULL
      )
),
expected AS (
    SELECT
        item_id,
        location_id,
        holder_user_id,
        sum(quantity_delta) AS quantity
    FROM journal_delta
    GROUP BY item_id, location_id, holder_user_id
    HAVING sum(quantity_delta) <> 0
)
SELECT
    coalesce(expected.item_id, actual.item_id) AS item_id,
    coalesce(expected.location_id, actual.location_id) AS location_id,
    coalesce(expected.holder_user_id, actual.holder_user_id) AS holder_user_id,
    expected.quantity AS journal_quantity,
    actual.quantity AS projection_quantity
FROM expected
FULL OUTER JOIN stock_balances AS actual
    ON actual.item_id = expected.item_id
   AND actual.location_id IS NOT DISTINCT FROM expected.location_id
   AND actual.holder_user_id IS NOT DISTINCT FROM expected.holder_user_id
WHERE expected.quantity IS DISTINCT FROM actual.quantity
ORDER BY item_id, location_id, holder_user_id;

WITH latest_serial_line AS (
    SELECT
        ml.inventory_unit_id,
        ml.serial_number_snapshot,
        ml.wwn_snapshot,
        m.movement_type,
        m.destination_location_id,
        m.destination_holder_user_id,
        row_number() OVER (
            PARTITION BY ml.inventory_unit_id
            ORDER BY m.journal_seq DESC
        ) AS latest_rank
    FROM movement_lines AS ml
    JOIN movements AS m ON m.id = ml.movement_id
    WHERE ml.item_accounting_mode = 'SERIAL'
),
expected AS (
    SELECT
        inventory_unit_id,
        CASE
            WHEN destination_location_id IS NOT NULL THEN 'STORED'
            WHEN destination_holder_user_id IS NOT NULL THEN 'ISSUED'
            WHEN movement_type = 'WRITE_OFF' THEN 'WRITTEN_OFF'
            ELSE 'VOIDED'
        END AS state,
        destination_location_id AS location_id,
        destination_holder_user_id AS holder_user_id,
        serial_number_snapshot AS serial_number,
        wwn_snapshot AS wwn
    FROM latest_serial_line
    WHERE latest_rank = 1
)
SELECT
    unit.id AS inventory_unit_id,
    expected.state AS journal_state,
    unit.state AS projection_state,
    expected.location_id AS journal_location_id,
    unit.current_location_id AS projection_location_id,
    expected.holder_user_id AS journal_holder_user_id,
    unit.current_holder_user_id AS projection_holder_user_id,
    expected.serial_number AS journal_serial_number,
    unit.serial_number AS projection_serial_number,
    expected.wwn AS journal_wwn,
    unit.wwn AS projection_wwn
FROM inventory_units AS unit
FULL OUTER JOIN expected ON expected.inventory_unit_id = unit.id
WHERE expected.inventory_unit_id IS NULL
   OR unit.id IS NULL
   OR expected.state IS DISTINCT FROM unit.state
   OR expected.location_id IS DISTINCT FROM unit.current_location_id
   OR expected.holder_user_id IS DISTINCT FROM unit.current_holder_user_id
   OR expected.serial_number IS DISTINCT FROM unit.serial_number
   OR expected.wwn IS DISTINCT FROM unit.wwn
ORDER BY inventory_unit_id;
