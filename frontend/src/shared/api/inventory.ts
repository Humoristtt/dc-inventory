import { ApiRequestError } from "./auth";

export type LocationPosition = {
  location_id: string;
  code: string;
  name: string;
};

export type UserPosition = {
  user_id: string;
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
  serial_number: string;
  wwn: string | null;
  comment: string | null;
  state: InventoryUnitState;
  location: LocationPosition | null;
  holder: UserPosition | null;
  created_at: string;
  updated_at: string;
};

type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type InventoryPositionQuery = {
  itemId?: string;
  locationId?: string;
  holderUserId?: string;
};

export type InventoryUnitQuery = InventoryPositionQuery & {
  state?: InventoryUnitState;
};

const PAGE_SIZE = 200;

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiRequestError(response.status, `HTTP ${response.status}`);
  }
  return await response.json() as T;
}

function inventoryParams(
  query: InventoryPositionQuery,
  offset: number,
): URLSearchParams {
  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offset),
  });
  if (query.itemId !== undefined) params.set("item_id", query.itemId);
  if (query.locationId !== undefined) params.set("location_id", query.locationId);
  if (query.holderUserId !== undefined) params.set("holder_user_id", query.holderUserId);
  return params;
}

async function getPage<T>(url: string, signal?: AbortSignal): Promise<Page<T>> {
  const response = await fetch(url, {
    credentials: "same-origin",
    signal,
  });
  return readJson<Page<T>>(response);
}

async function getEveryPage<T>(
  load: (offset: number) => Promise<Page<T>>,
): Promise<T[]> {
  const items: T[] = [];
  let offset = 0;
  while (true) {
    const page = await load(offset);
    items.push(...page.items);
    offset += page.items.length;
    if (page.items.length === 0 || offset >= page.total) {
      return items;
    }
  }
}

export function getInventoryStock(
  query: InventoryPositionQuery,
  signal?: AbortSignal,
) {
  return getEveryPage<StockBalance>((offset) => {
    const params = inventoryParams(query, offset);
    return getPage<StockBalance>(`/api/inventory/stock?${params.toString()}`, signal);
  });
}

export function getInventoryUnits(
  query: InventoryUnitQuery,
  signal?: AbortSignal,
) {
  return getEveryPage<InventoryUnit>((offset) => {
    const params = inventoryParams(query, offset);
    if (query.state !== undefined) params.set("state", query.state);
    return getPage<InventoryUnit>(`/api/inventory/units?${params.toString()}`, signal);
  });
}
