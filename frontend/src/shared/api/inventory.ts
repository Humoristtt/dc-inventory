import { ApiRequestError } from "./auth";

export type LocationPosition = {
  location_id: string;
  code: string;
  name: string;
};

export type UserPosition = {
  user_id: string | null;
  display_name: string;
};

export type StockBalance = {
  id: string;
  item_id: string;
  item_name: string;
  quantity: number;
  location: LocationPosition | null;
  holder: UserPosition | null;
  updated_at: string;
};

export type InventoryUnitState = "STORED" | "ISSUED" | "WRITTEN_OFF" | "VOIDED";

export type InventoryUnit = {
  id: string;
  item_id: string;
  item_name: string;
  serial_number: string | null;
  wwn: string | null;
  comment: string | null;
  state: InventoryUnitState;
  location: LocationPosition | null;
  holder: UserPosition | null;
  created_at: string;
  updated_at: string;
};

export type InventoryPage<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type InventorySummary = {
  available_count: number;
  custody_count: number;
  total_count: number;
};

export type MyEquipmentSerialPreview = {
  id: string;
  serial_number: string;
  wwn: string | null;
};

export type MyEquipmentPosition = {
  item_id: string;
  item_name: string;
  accounting_mode: "QUANTITY" | "SERIAL";
  quantity: number;
  serial_count: number;
  serial_preview: MyEquipmentSerialPreview[];
};

export type MyEquipmentPage = InventoryPage<MyEquipmentPosition>;

export type InventoryPositionQuery = {
  itemId?: string;
  locationId?: string;
  holderUserId?: string;
};

export type InventoryUnitQuery = InventoryPositionQuery & {
  state?: InventoryUnitState;
};

export type InventoryPagination = {
  limit?: number;
  offset?: number;
};

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiRequestError(response.status, `HTTP ${response.status}`);
  }
  return await response.json() as T;
}

function inventoryParams(
  query: InventoryPositionQuery,
  pagination: InventoryPagination,
): URLSearchParams {
  const params = new URLSearchParams({
    limit: String(pagination.limit ?? 50),
    offset: String(pagination.offset ?? 0),
  });

  if (query.itemId !== undefined) params.set("item_id", query.itemId);
  if (query.locationId !== undefined) params.set("location_id", query.locationId);
  if (query.holderUserId !== undefined) params.set("holder_user_id", query.holderUserId);

  return params;
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    credentials: "same-origin",
    signal,
  });
  return readJson<T>(response);
}

export function getInventorySummary(
  itemId: string,
  signal?: AbortSignal,
) {
  return getJson<InventorySummary>(
    `/api/inventory/items/${encodeURIComponent(itemId)}/summary`,
    signal,
  );
}

export function getInventoryStockPage(
  query: InventoryPositionQuery,
  pagination: InventoryPagination = {},
  signal?: AbortSignal,
) {
  const params = inventoryParams(query, pagination);
  return getJson<InventoryPage<StockBalance>>(
    `/api/inventory/stock?${params.toString()}`,
    signal,
  );
}

export function getInventoryUnitsPage(
  query: InventoryUnitQuery,
  pagination: InventoryPagination = {},
  signal?: AbortSignal,
) {
  const params = inventoryParams(query, pagination);
  if (query.state !== undefined) params.set("state", query.state);

  return getJson<InventoryPage<InventoryUnit>>(
    `/api/inventory/units?${params.toString()}`,
    signal,
  );
}

export function getMyEquipmentPage(
  pagination: InventoryPagination = {},
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({
    limit: String(pagination.limit ?? 20),
    offset: String(pagination.offset ?? 0),
  });

  return getJson<MyEquipmentPage>(
    `/api/inventory/mine?${params.toString()}`,
    signal,
  );
}
