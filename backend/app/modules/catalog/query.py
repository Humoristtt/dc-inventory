"""Public catalog query façade.

Query implementation is split by responsibility:
- query_spec.py: request parsing, category scope, and controlled predicates;
- query_predicates.py: shared item/filter predicates;
- query_items.py: paginated catalog item reads and ordering;
- query_facets.py: facet aggregation.
"""

from app.modules.catalog.query_facets import query_catalog_facets
from app.modules.catalog.query_items import query_catalog_items
from app.modules.catalog.query_spec import (
    _normalize_query_tokens,
    build_catalog_query_spec,
    equipment_scope,
    long_range_predicate,
    rj45_transceiver_predicate,
    scope_category_ids,
)
from app.modules.catalog.query_types import (
    DEFAULT_FACET_VALUE_LIMIT,
    MAX_FACET_VALUE_LIMIT,
    MAX_FILTER_EXPRESSION_LENGTH,
    MAX_QUERY_VALUES,
    MAX_SEARCH_TOKENS,
    AttributeFilter,
    CatalogItemPage,
    CatalogListRecord,
    CatalogQuerySpec,
    FacetBound,
    FacetRecord,
    FacetValue,
    FacetValueRecord,
    InventorySummary,
)
from app.modules.catalog.validation import (
    CatalogSchemaError,
    CatalogValidationError,
)

__all__ = (
    "DEFAULT_FACET_VALUE_LIMIT",
    "MAX_FACET_VALUE_LIMIT",
    "MAX_FILTER_EXPRESSION_LENGTH",
    "MAX_QUERY_VALUES",
    "MAX_SEARCH_TOKENS",
    "AttributeFilter",
    "CatalogItemPage",
    "CatalogListRecord",
    "CatalogQuerySpec",
    "CatalogSchemaError",
    "CatalogValidationError",
    "FacetBound",
    "FacetRecord",
    "FacetValue",
    "FacetValueRecord",
    "InventorySummary",
    "_normalize_query_tokens",
    "build_catalog_query_spec",
    "equipment_scope",
    "long_range_predicate",
    "query_catalog_facets",
    "query_catalog_items",
    "rj45_transceiver_predicate",
    "scope_category_ids",
)
