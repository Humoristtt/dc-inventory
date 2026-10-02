"""Public inventory service façade.

Implementation is split by responsibility:
- locations.py: location mutations;
- movements.py: warehouse movement mutations;
- queries.py: read paths;
- domain.py: errors, records, and normalization helpers.
"""

from app.modules.inventory.domain import (
    InventoryConflictError,
    InventoryError,
    InventoryNotFoundError,
    InventoryValidationError,
    LocationPage,
    MovementCursorPage,
    MovementFeedSnapshot,
    MovementPage,
    MovementRecord,
    MovementResult,
    StockBalancePage,
    StockBalanceRecord,
    display_identity,
    normalize_inline_text,
    normalize_optional_text,
)
from app.modules.inventory.locations import (
    create_location,
    set_location_archived,
    update_location,
)
from app.modules.inventory.movements import (
    create_movement,
    reverse_movement,
    validate_positions,
)
from app.modules.inventory.queries import (
    acquire_movement_feed_snapshot,
    get_location,
    get_movement_record,
    list_locations,
    list_movements,
    list_movements_cursor,
    list_stock_balances,
)

__all__ = (
    "InventoryConflictError",
    "InventoryError",
    "InventoryNotFoundError",
    "InventoryValidationError",
    "LocationPage",
    "MovementCursorPage",
    "MovementFeedSnapshot",
    "MovementPage",
    "MovementRecord",
    "MovementResult",
    "StockBalancePage",
    "StockBalanceRecord",
    "acquire_movement_feed_snapshot",
    "create_location",
    "create_movement",
    "display_identity",
    "get_location",
    "get_movement_record",
    "list_locations",
    "list_movements",
    "list_movements_cursor",
    "list_stock_balances",
    "normalize_inline_text",
    "normalize_optional_text",
    "reverse_movement",
    "set_location_archived",
    "update_location",
    "validate_positions",
)
