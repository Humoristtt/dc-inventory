import { ApiRequestError } from "./auth";

export type AccountingMode = "QUANTITY" | "SERIAL";
export type ItemStatus = "ACTIVE" | "ARCHIVED";
export type AttributeDataType =
  | "TEXT"
  | "INTEGER"
  | "DECIMAL"
  | "BOOLEAN"
  | "ENUM";
export type FilterType = "NONE" | "EXACT" | "RANGE";
export type Availability = "ANY" | "IN_STOCK" | "OUT_OF_STOCK";
export type ItemSort = "name" | "manufacturer" | "available" | "total";
export type SortOrder = "asc" | "desc";
export type AttributeFilterOperator = "eq" | "gte" | "lte";
export type CatalogScalar = string | number | boolean;

export type CategorySummary = {
  id: string;
  key: string;
  display_name: string;
  description: string | null;
  default_accounting_mode: AccountingMode;
  sort_order: number;
  is_system: boolean;
};

export type CategoryAttribute = {
  id: string;
  key: string;
  label: string;
  data_type: AttributeDataType;
  unit: string | null;
  required: boolean;
  filterable: boolean;
  searchable: boolean;
  card_visible: boolean;
  detail_visible: boolean;
  table_visible: boolean;
  excel_visible: boolean;
  sort_order: number;
  filter_type: FilterType;
  allowed_values: string[] | null;
  validation_metadata: Record<string, CatalogScalar> | null;
  is_system: boolean;
};

export type CategoryDetail = CategorySummary & {
  attributes: CategoryAttribute[];
};

export type Manufacturer = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
};

export type ManufacturerPage = {
  items: Manufacturer[];
  total: number;
  limit: number;
  offset: number;
};

export type ItemCategory = {
  id: string;
  key: string;
  display_name: string;
};

export type ItemManufacturer = {
  id: string;
  name: string;
};

export type CatalogItem = {
  id: string;
  category: ItemCategory;
  manufacturer: ItemManufacturer | null;
  name: string;
  model: string | null;
  manufacturer_part_number: string | null;
  internal_code: string | null;
  description: string | null;
  accounting_mode: AccountingMode;
  status: ItemStatus;
  comment: string | null;
  datasheet_url: string | null;
  technical_data_source: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  attributes: Record<string, CatalogScalar>;
};

export type InventorySummary = {
  available_count: number;
  custody_count: number;
  total_count: number;
};

export type CatalogItemListEntry = CatalogItem & {
  inventory: InventorySummary;
};

export type CatalogItemPage = {
  items: CatalogItemListEntry[];
  total: number;
  limit: number;
  offset: number;
};

export type FacetValue = {
  value: CatalogScalar;
  count: number;
  label: string | null;
  code: string | null;
  name: string | null;
};

export type CatalogFacet = {
  key: string;
  label: string;
  data_type: AttributeDataType;
  unit: string | null;
  filter_type: FilterType;
  values: FacetValue[];
  min: string | number | null;
  max: string | number | null;
};

export type CatalogFacetList = {
  facets: CatalogFacet[];
};

export type CatalogAttributeFilter = {
  key: string;
  operator: AttributeFilterOperator;
  value: string;
};

export type ItemWritePayload = {
  category_key: string;
  manufacturer_id: string | null;
  name: string;
  model: string | null;
  manufacturer_part_number: string | null;
  internal_code: string | null;
  description: string | null;
  accounting_mode: AccountingMode | null;
  comment: string | null;
  datasheet_url: string | null;
  technical_data_source: string | null;
  attributes: Record<string, CatalogScalar>;
};

export type ItemPatchPayload = Partial<
  Omit<ItemWritePayload, "category_key" | "accounting_mode">
>;

export type DuplicateCandidate = {
  item_id: string;
  name: string;
  model: string | null;
  manufacturer_id: string | null;
  manufacturer_name: string | null;
  manufacturer_part_number: string | null;
  reason: string;
};

export type DuplicateCheckPayload = {
  category_key: string;
  manufacturer_id: string | null;
  manufacturer_part_number: string | null;
  name: string;
  model: string | null;
  exclude_item_id?: string;
};

export type DuplicateCheckResult = {
  candidates: DuplicateCandidate[];
};

export type CatalogQuery = {
  q?: string;
  category?: string;
  status?: ItemStatus;
  manufacturerIds?: readonly string[];
  availability?: Availability;
  locationIds?: readonly string[];
  filters?: readonly CatalogAttributeFilter[];
  sort?: ItemSort;
  order?: SortOrder;
  limit?: number;
  offset?: number;
};

function uniqueSorted(values: readonly string[] | undefined): string[] {
  return [...new Set(values ?? [])].sort((left, right) =>
    left.localeCompare(right),
  );
}

function sortedFilters(
  filters: readonly CatalogAttributeFilter[] | undefined,
): CatalogAttributeFilter[] {
  return [...(filters ?? [])].sort((left, right) => {
    const leftKey = `${left.key}:${left.operator}:${left.value}`;
    const rightKey = `${right.key}:${right.operator}:${right.value}`;
    return leftKey.localeCompare(rightKey);
  });
}

type EncodeCatalogQueryOptions = {
  includePagination?: boolean;
  includeSorting?: boolean;
};

export function encodeCatalogQuery(
  query: CatalogQuery,
  {
    includePagination = true,
    includeSorting = true,
  }: EncodeCatalogQueryOptions = {},
): URLSearchParams {
  const params = new URLSearchParams();
  const search = query.q?.trim();

  if (search) {
    params.set("q", search);
  }
  if (query.category) {
    params.set("category", query.category);
  }
  if (query.status) {
    params.set("status", query.status);
  }
  for (const manufacturerId of uniqueSorted(query.manufacturerIds)) {
    params.append("manufacturer_id", manufacturerId);
  }
  if (query.availability && query.availability !== "ANY") {
    params.set("availability", query.availability);
  }
  for (const locationId of uniqueSorted(query.locationIds)) {
    params.append("location_id", locationId);
  }
  for (const filter of sortedFilters(query.filters)) {
    params.append(
      "filter",
      `${filter.key}:${filter.operator}:${filter.value}`,
    );
  }
  if (includeSorting) {
    params.set("sort", query.sort ?? "name");
    params.set("order", query.order ?? "asc");
  }
  if (includePagination) {
    params.set("limit", String(query.limit ?? 20));
    params.set("offset", String(query.offset ?? 0));
  }

  return params;
}

export function catalogQueryCacheKey(query: CatalogQuery): string {
  return encodeCatalogQuery(
    { ...query, limit: undefined, offset: undefined },
    { includePagination: false },
  ).toString();
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let code: string | undefined;
    let message = `HTTP ${response.status}`;
    try {
      const payload = await response.json() as {
        detail?: string | { code?: string; message?: string };
      };
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (payload.detail !== undefined) {
        code = payload.detail.code;
        message = payload.detail.message ?? message;
      }
    } catch {
      // Non-JSON proxy responses keep the stable HTTP fallback.
    }
    throw new ApiRequestError(response.status, message, code);
  }
  return (await response.json()) as T;
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    credentials: "same-origin",
    signal,
  });
  return readJson<T>(response);
}

async function sendJson<T>(
  url: string,
  method: "POST" | "PATCH",
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  return readJson<T>(response);
}

export function getCatalogCategories(signal?: AbortSignal) {
  return getJson<CategorySummary[]>("/api/catalog/categories", signal);
}

export function getCatalogCategory(
  categoryKey: string,
  signal?: AbortSignal,
) {
  return getJson<CategoryDetail>(
    `/api/catalog/categories/${encodeURIComponent(categoryKey)}`,
    signal,
  );
}

export function getCatalogManufacturers(
  {
    limit = 100,
    offset = 0,
    q,
  }: {
    limit?: number;
    offset?: number;
    q?: string;
  } = {},
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });

  if (q !== undefined && q.trim() !== "") {
    params.set("q", q.trim());
  }

  return getJson<ManufacturerPage>(
    `/api/catalog/manufacturers?${params.toString()}`,
    signal,
  );
}

export function getCatalogItems(query: CatalogQuery, signal?: AbortSignal) {
  const params = encodeCatalogQuery(query);
  return getJson<CatalogItemPage>(
    `/api/catalog/items?${params.toString()}`,
    signal,
  );
}

export function getCatalogFacets(query: CatalogQuery, signal?: AbortSignal) {
  const params = encodeCatalogQuery(query, {
    includePagination: false,
    includeSorting: false,
  });
  return getJson<CatalogFacetList>(
    `/api/catalog/items/facets?${params.toString()}`,
    signal,
  );
}

export function getCatalogItem(itemId: string, signal?: AbortSignal) {
  return getJson<CatalogItem>(
    `/api/catalog/items/${encodeURIComponent(itemId)}`,
    signal,
  );
}

export function createCatalogManufacturer(name: string, signal?: AbortSignal) {
  return sendJson<Manufacturer>(
    "/api/admin/catalog/manufacturers",
    "POST",
    { name },
    signal,
  );
}

export function checkCatalogDuplicates(
  payload: DuplicateCheckPayload,
  signal?: AbortSignal,
) {
  return sendJson<DuplicateCheckResult>(
    "/api/admin/catalog/items/check-duplicates",
    "POST",
    payload,
    signal,
  );
}

export function createCatalogItem(
  payload: ItemWritePayload,
  signal?: AbortSignal,
) {
  return sendJson<CatalogItem>(
    "/api/admin/catalog/items",
    "POST",
    payload,
    signal,
  );
}

export function patchCatalogItem(
  itemId: string,
  payload: ItemPatchPayload,
  signal?: AbortSignal,
) {
  return sendJson<CatalogItem>(
    `/api/admin/catalog/items/${encodeURIComponent(itemId)}`,
    "PATCH",
    payload,
    signal,
  );
}

export function setCatalogItemArchived(
  itemId: string,
  archived: boolean,
  signal?: AbortSignal,
) {
  return sendJson<CatalogItem>(
    `/api/admin/catalog/items/${encodeURIComponent(itemId)}/${archived ? "archive" : "unarchive"}`,
    "POST",
    {},
    signal,
  );
}
