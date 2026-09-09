-- Read-only: zero rows means both mutable projections match the journal.
WITH stock_deltas AS (
    SELECT line.item_id, movement.source_location_id AS location_id, -line.quantity AS delta
    FROM movement_lines line JOIN movements movement ON movement.id = line.movement_id
    WHERE movement.source_location_id IS NOT NULL
    UNION ALL
    SELECT line.item_id, movement.destination_location_id, line.quantity
    FROM movement_lines line JOIN movements movement ON movement.id = line.movement_id
    WHERE movement.destination_location_id IS NOT NULL
), expected_stock AS (
    SELECT item_id, location_id, sum(delta) AS quantity
    FROM stock_deltas GROUP BY item_id, location_id HAVING sum(delta) <> 0
), stock_drift AS (
    SELECT
        'stock'::text AS projection,
        coalesce(expected.item_id, actual.item_id) AS item_id,
        coalesce(expected.location_id, actual.location_id) AS location_id,
        NULL::uuid AS user_id,
        coalesce(expected.quantity, 0) AS journal_quantity,
        coalesce(actual.quantity, 0) AS projected_quantity
    FROM expected_stock expected
    FULL JOIN stock_balances actual USING (item_id, location_id)
    WHERE coalesce(expected.quantity, 0) <> coalesce(actual.quantity, 0)
), custody_deltas AS (
    SELECT
        line.item_id,
        movement.custody_user_id AS user_id,
        CASE
            WHEN movement.movement_type = 'ISSUE' THEN line.quantity
            WHEN movement.movement_type = 'RETURN' THEN -line.quantity
            WHEN movement.movement_type = 'REVERSAL'
                 AND original.movement_type = 'ISSUE' THEN -line.quantity
            WHEN movement.movement_type = 'REVERSAL'
                 AND original.movement_type = 'RETURN' THEN line.quantity
        END AS delta
    FROM movement_lines line
    JOIN movements movement ON movement.id = line.movement_id
    LEFT JOIN movements original ON original.id = movement.original_movement_id
    WHERE movement.custody_user_id IS NOT NULL
), expected_custody AS (
    SELECT item_id, user_id, sum(delta) AS quantity
    FROM custody_deltas
    GROUP BY item_id, user_id
    HAVING sum(delta) <> 0
), custody_drift AS (
    SELECT
        'custody'::text AS projection,
        coalesce(expected.item_id, actual.item_id) AS item_id,
        NULL::uuid AS location_id,
        coalesce(expected.user_id, actual.user_id) AS user_id,
        coalesce(expected.quantity, 0) AS journal_quantity,
        coalesce(actual.quantity, 0) AS projected_quantity
    FROM expected_custody expected
    FULL JOIN user_item_custody_balances actual USING (item_id, user_id)
    WHERE coalesce(expected.quantity, 0) <> coalesce(actual.quantity, 0)
)
SELECT * FROM stock_drift
UNION ALL
SELECT * FROM custody_drift
ORDER BY projection, item_id, location_id, user_id;
