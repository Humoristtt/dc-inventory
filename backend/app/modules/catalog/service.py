"""Public catalog service façade.

Implementation is split by responsibility:
- item_validation.py: batched item identity and schema validation;
- read_service.py: categories, manufacturers, item reads, and duplicate checks;
- mutations.py: manufacturer and item mutations;
- records.py: service result records.
"""

from app.modules.catalog.item_validation import (
    ItemCreateValidationContext,
    load_item_create_validation_context,
    validate_item_create_payload,
)
from app.modules.catalog.mutations import (
    create_item,
    create_manufacturer,
    delete_unused_item,
    set_item_archived,
    update_item,
)
from app.modules.catalog.read_service import (
    check_duplicate_candidates,
    get_category_by_key,
    get_category_record,
    get_item_record,
    list_categories,
    list_items,
    list_manufacturers,
    load_attributes_for_items,
)
from app.modules.catalog.records import (
    CategoryRecord,
    DuplicateCandidate,
    ItemPage,
    ItemRecord,
    ManufacturerPage,
    ValidatedItemDraft,
)
from app.modules.catalog.validation import (
    MAX_DECIMAL_INTEGRAL_DIGITS,
    MAX_DECIMAL_SCALE,
    MAX_SAFE_INTEGER,
    MIN_SAFE_INTEGER,
    CatalogConflictError,
    CatalogError,
    CatalogItemInUseError,
    CatalogNotFoundError,
    CatalogSchemaError,
    CatalogValidationError,
)

__all__ = (
    "MAX_DECIMAL_INTEGRAL_DIGITS",
    "MAX_DECIMAL_SCALE",
    "MAX_SAFE_INTEGER",
    "MIN_SAFE_INTEGER",
    "CatalogConflictError",
    "CatalogError",
    "CatalogItemInUseError",
    "CatalogNotFoundError",
    "CatalogSchemaError",
    "CatalogValidationError",
    "CategoryRecord",
    "DuplicateCandidate",
    "ItemCreateValidationContext",
    "ItemPage",
    "ItemRecord",
    "ManufacturerPage",
    "ValidatedItemDraft",
    "check_duplicate_candidates",
    "create_item",
    "create_manufacturer",
    "delete_unused_item",
    "get_category_by_key",
    "get_category_record",
    "get_item_record",
    "list_categories",
    "list_items",
    "list_manufacturers",
    "load_attributes_for_items",
    "load_item_create_validation_context",
    "set_item_archived",
    "update_item",
    "validate_item_create_payload",
)
