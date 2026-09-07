-- Read-only: zero rows means the location-only projection matches the journal.
WITH deltas AS (
    SELECT line.item_id, movement.source_location_id AS location_id, -line.quantity AS delta
    FROM movement_lines line JOIN movements movement ON movement.id = line.movement_id
    WHERE movement.source_location_id IS NOT NULL
    UNION ALL
    SELECT line.item_id, movement.destination_location_id, line.quantity
    FROM movement_lines line JOIN movements movement ON movement.id = line.movement_id
    WHERE movement.destination_location_id IS NOT NULL
), expected AS (
    SELECT item_id, location_id, sum(delta) AS quantity
    FROM deltas GROUP BY item_id, location_id HAVING sum(delta) <> 0
)
SELECT coalesce(expected.item_id, actual.item_id) AS item_id,
       coalesce(expected.location_id, actual.location_id) AS location_id,
       coalesce(expected.quantity, 0) AS journal_quantity,
       coalesce(actual.quantity, 0) AS projected_quantity
FROM expected FULL JOIN stock_balances actual USING (item_id, location_id)
WHERE coalesce(expected.quantity, 0) <> coalesce(actual.quantity, 0)
ORDER BY item_id, location_id;
