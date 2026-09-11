import type {
  Availability,
  CatalogAttributeFilter,
  CatalogQuery,
  ItemSort,
  ItemStatus,
  SortOrder,
} from "../../shared/api/catalog";

export type CatalogViewState = {
  q: string;
  status: ItemStatus;
  manufacturerIds: string[];
  availability: Availability;
  locationIds: string[];
  filters: CatalogAttributeFilter[];
  sort: ItemSort;
  order: SortOrder;
};

export type CatalogFilterState = Pick<
  CatalogViewState,
  | "status"
  | "manufacturerIds"
  | "availability"
  | "locationIds"
  | "filters"
>;

export type CatalogSortState = Pick<CatalogViewState, "sort" | "order">;

export const defaultCatalogSort: CatalogSortState = {
  sort: "name",
  order: "asc",
};

export const defaultCatalogViewState: CatalogViewState = {
  q: "",
  status: "ACTIVE",
  manufacturerIds: [],
  availability: "ANY",
  locationIds: [],
  filters: [],
  sort: defaultCatalogSort.sort,
  order: defaultCatalogSort.order,
};

export const defaultCatalogFilterState: CatalogFilterState = {
  status: defaultCatalogViewState.status,
  manufacturerIds: [],
  availability: defaultCatalogViewState.availability,
  locationIds: [],
  filters: [],
};

const itemSorts = new Set<ItemSort>([
  "name",
  "manufacturer",
  "available",
  "total",
  "speed",
]);

function uniqueSorted(values: string[]): string[] {
  return [...new Set(values)].sort((left, right) => left.localeCompare(right));
}

export function parseAttributeFilter(
  expression: string,
): CatalogAttributeFilter | null {
  const firstSeparator = expression.indexOf(":");
  const secondSeparator = expression.indexOf(":", firstSeparator + 1);
  if (firstSeparator <= 0 || secondSeparator <= firstSeparator + 1) {
    return null;
  }

  const key = expression.slice(0, firstSeparator).trim();
  const operator = expression.slice(firstSeparator + 1, secondSeparator);
  const value = expression.slice(secondSeparator + 1);
  if (
    key === ""
    || value === ""
    || (operator !== "eq" && operator !== "gte" && operator !== "lte")
  ) {
    return null;
  }
  return { key, operator, value };
}

export function readCatalogViewState(
  params: URLSearchParams,
  defaultSort: CatalogSortState = defaultCatalogSort,
): CatalogViewState {
  const availabilityValue = params.get("availability");
  const availability: Availability =
    availabilityValue === "IN_STOCK" || availabilityValue === "OUT_OF_STOCK"
      ? availabilityValue
      : "ANY";
  const sortValue = params.get("sort") as ItemSort | null;
  const orderValue = params.get("order");
  const statusValue = params.get("status");
  const explicitSort =
    sortValue !== null && itemSorts.has(sortValue);

  const sort = explicitSort
    ? sortValue
    : defaultSort.sort;

  const order: SortOrder =
    orderValue === "asc" || orderValue === "desc"
      ? orderValue
      : explicitSort
        ? "asc"
        : defaultSort.order;

  return {
    q: params.get("q")?.trim() ?? "",
    status: statusValue === "ARCHIVED" ? "ARCHIVED" : "ACTIVE",
    manufacturerIds: uniqueSorted(params.getAll("manufacturer_id")),
    availability,
    locationIds: uniqueSorted(params.getAll("location_id")),
    filters: params
      .getAll("filter")
      .map(parseAttributeFilter)
      .filter((filter): filter is CatalogAttributeFilter => filter !== null)
      .sort((left, right) =>
        `${left.key}:${left.operator}:${left.value}`.localeCompare(
          `${right.key}:${right.operator}:${right.value}`,
        ),
      ),
    sort,
    order,
  };
}

export function catalogViewStateToSearchParams(
  state: CatalogViewState,
  defaultSort: CatalogSortState = defaultCatalogSort,
): URLSearchParams {
  const params = new URLSearchParams();
  const q = state.q.trim();
  if (q) {
    params.set("q", q);
  }
  if (state.status !== "ACTIVE") {
    params.set("status", state.status);
  }
  for (const manufacturerId of uniqueSorted(state.manufacturerIds)) {
    params.append("manufacturer_id", manufacturerId);
  }
  if (state.availability !== "ANY") {
    params.set("availability", state.availability);
  }
  for (const locationId of uniqueSorted(state.locationIds)) {
    params.append("location_id", locationId);
  }
  for (const filter of [...state.filters].sort((left, right) =>
    `${left.key}:${left.operator}:${left.value}`.localeCompare(
      `${right.key}:${right.operator}:${right.value}`,
    ),
  )) {
    params.append("filter", `${filter.key}:${filter.operator}:${filter.value}`);
  }
  if (state.sort !== defaultSort.sort) {
    params.set("sort", state.sort);
  }

  const implicitOrder =
    state.sort === defaultSort.sort
      ? defaultSort.order
      : "asc";

  if (state.order !== implicitOrder) {
    params.set("order", state.order);
  }
  return params;
}

export function toCatalogQuery(
  state: CatalogViewState,
  category?: string,
): CatalogQuery {
  return {
    q: state.q,
    category,
    status: state.status,
    manufacturerIds: state.manufacturerIds,
    availability: state.availability,
    locationIds: state.locationIds,
    filters: state.filters,
    sort: state.sort,
    order: state.order,
  };
}

export function activeFilterCount(state: CatalogViewState): number {
  return (
    state.manufacturerIds.length
    + state.locationIds.length
    + state.filters.length
    + (state.availability === "ANY" ? 0 : 1)
    + (state.status === "ACTIVE" ? 0 : 1)
  );
}

export function catalogFiltersFromViewState(
  state: CatalogViewState,
): CatalogFilterState {
  return {
    status: state.status,
    manufacturerIds: [...state.manufacturerIds],
    availability: state.availability,
    locationIds: [...state.locationIds],
    filters: state.filters.map((filter) => ({ ...filter })),
  };
}

export function withCatalogFilters(
  state: CatalogViewState,
  filters: CatalogFilterState,
): CatalogViewState {
  return {
    ...state,
    status: filters.status,
    manufacturerIds: [...filters.manufacturerIds],
    availability: filters.availability,
    locationIds: [...filters.locationIds],
    filters: filters.filters.map((filter) => ({ ...filter })),
  };
}

export function withCatalogSort(
  state: CatalogViewState,
  selection: CatalogSortState,
): CatalogViewState {
  return { ...state, ...selection };
}

export function withoutFilters(state: CatalogViewState): CatalogViewState {
  return withCatalogFilters(state, defaultCatalogFilterState);
}
