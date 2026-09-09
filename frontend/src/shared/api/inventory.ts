import { ApiRequestError } from "./auth";

export type LocationPosition = { location_id: string; code: string; name: string };
export type StockBalance = { id: string; item_id: string; item_name: string; quantity: number; location: LocationPosition; updated_at: string };
export type InventorySummary = { total_count: number; locations: StockBalance[] };
export type InventoryPage<T> = { items: T[]; total: number; limit: number; offset: number };
export type MovementCursorPage<T> = { items: T[]; limit: number; next_before_journal_seq: number | null; snapshot_at?: string };
export type StorageLocation = { id: string; code: string; name: string; location_type: "WAREHOUSE" | "DATACENTER"; address: string | null; status: "ACTIVE" | "ARCHIVED" };
export type MovementType = "ISSUE" | "RETURN" | "TRANSFER" | "RECEIPT" | "WRITE_OFF" | "CORRECTION" | "REVERSAL";
export type Movement = {
  id: string; journal_seq: number; occurred_at: string; actor_user_id: string;
  actor_display_name_snapshot: string; movement_type: MovementType;
  source_location_name_snapshot: string | null; destination_location_name_snapshot: string | null;
  lines: { id: string; item_id: string; item_name_snapshot: string; quantity: number }[];
};
export type MovementInput = { movement_type: MovementType; client_request_id: string;
  source_location_id?: string; destination_location_id?: string; lines: { item_id: string; quantity: number }[] };

export async function inventoryRequest<T>(url: string, body?: unknown, method = "POST", signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin", signal,
    ...(body !== undefined ? { method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) } : {}) });
  if (!response.ok) {
    let code: string | undefined;
    try { const error = await response.json(); code = error.detail?.code; } catch { /* HTTP fallback */ }
    throw new ApiRequestError(response.status, `HTTP ${response.status}`, code);
  }
  return response.json() as Promise<T>;
}
export function inventoryError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 423) return "Складские изменения пока отключены администратором.";
    if (error.code === "insufficient_stock") return "Недостаточно оборудования в выбранном месте хранения. Обновите остаток.";
    if (error.code === "location_not_empty") return "Сначала переместите или спишите остаток в этом месте хранения.";
    if (error.status === 403) return "Недостаточно прав для этой операции.";
    if (error.status === 409) return "Данные изменились. Обновите страницу и проверьте операцию.";
  }
  return "Не удалось выполнить операцию. Проверьте данные и соединение.";
}
export const movementLabels: Record<MovementType, string> = { ISSUE: "Взял", RETURN: "Вернул", TRANSFER: "Перемещение", RECEIPT: "Приход", WRITE_OFF: "Списание", CORRECTION: "Корректировка", REVERSAL: "Отмена операции" };
export function getInventorySummary(itemId: string, signal?: AbortSignal) {
  return inventoryRequest<InventorySummary>(`/api/inventory/items/${encodeURIComponent(itemId)}/summary`, undefined, "GET", signal);
}
export async function getLocations(signal?: AbortSignal): Promise<StorageLocation[]> {
  const items: StorageLocation[] = [];
  let offset = 0;
  for (;;) {
    const page = await inventoryRequest<InventoryPage<StorageLocation>>(`/api/inventory/locations?limit=200&offset=${offset}`, undefined, "GET", signal);
    items.push(...page.items); offset += page.items.length;
    if (offset >= page.total || page.items.length === 0) return items;
  }
}
export function createMovement(body: MovementInput) { return inventoryRequest<Movement>("/api/inventory/movements", body); }
