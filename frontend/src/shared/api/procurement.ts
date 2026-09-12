import { ApiRequestError } from "./auth";

export type ProcurementStatus =
  | "AGREEMENT_PENDING_MANAGER"
  | "AGREEMENT_REVISION_REQUIRED"
  | "PURCHASING"
  | "AWAITING_ACCEPTANCE"
  | "COMPLETED";

export type ProcurementLineInput =
  | {
      line_type: "EXISTING_ITEM";
      item_id: string;
      quantity: number;
    }
  | {
      line_type: "PROPOSED_ITEM";
      category_key: string;
      manufacturer_id: string | null;
      name: string;
      model: string | null;
      attributes: Record<string, string | number | boolean>;
      quantity: number;
    };

export type UserSummary = { id: string; display_name: string };
export type ProcurementLine = {
  id: string;
  line_no: number;
  line_type: "EXISTING_ITEM" | "PROPOSED_ITEM";
  catalog_item_id: string | null;
  bound_item_id: string | null;
  display_snapshot: Record<string, unknown>;
  quantity: number;
};
export type ProcurementRevision = {
  id: string;
  revision_number: number;
  submitted_by: UserSummary;
  general_comment: string | null;
  created_at: string;
  lines: ProcurementLine[];
};
export type ProcurementEvent = {
  id: string;
  event_type: string;
  actor: UserSummary;
  from_status: ProcurementStatus | null;
  to_status: ProcurementStatus | null;
  revision_id: string | null;
  comment: string | null;
  metadata: Record<string, unknown> | null;
  occurred_at: string;
};
export type ProcurementSummary = {
  id: string;
  request_number: string;
  status: ProcurementStatus;
  status_label: string;
  initiator: UserSummary;
  assigned_manager: UserSummary;
  current_revision_id: string;
  revision_number: number;
  line_count: number;
  state_version: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};
export type ProcurementRequest = ProcurementSummary & {
  current_revision: ProcurementRevision;
  revisions: ProcurementRevision[];
  events: ProcurementEvent[];
  final_movement_id: string | null;
  available_actions: string[];
};
export type ProcurementPage = {
  items: ProcurementSummary[];
  total: number;
  limit: number;
  offset: number;
};
export type ManagerPage = {
  items: UserSummary[];
  total: number;
  limit: number;
  offset: number;
};

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    let code: string | undefined;
    try {
      const body = (await response.json()) as {
        detail?: string | { code?: string; message?: string };
      };
      if (typeof body.detail === "string") message = body.detail;
      else if (body.detail) {
        message = body.detail.message ?? message;
        code = body.detail.code;
      }
    } catch {
      // Keep the stable HTTP fallback for non-JSON proxy errors.
    }
    throw new ApiRequestError(response.status, message, code);
  }
  return response.json() as Promise<T>;
}

export async function procurementRequest<T>(
  url: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(url, {
    credentials: "same-origin",
    signal,
    ...(body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
  });
  return readJson<T>(response);
}

export function getProcurementRequests(
  view: "my" | "active" | "history",
  signal?: AbortSignal,
) {
  return procurementRequest<ProcurementPage>(
    `/api/procurement/requests?view=${view}&limit=30&offset=0`,
    undefined,
    signal,
  );
}

export function getProcurementRequest(id: string, signal?: AbortSignal) {
  return procurementRequest<ProcurementRequest>(
    `/api/procurement/requests/${encodeURIComponent(id)}`,
    undefined,
    signal,
  );
}

export function getProcurementManagers(signal?: AbortSignal) {
  return procurementRequest<ManagerPage>(
    "/api/procurement/managers?limit=200&offset=0",
    undefined,
    signal,
  );
}

export function createProcurementRequest(body: {
  assigned_manager_user_id: string;
  general_comment: string | null;
  client_request_id: string;
  lines: ProcurementLineInput[];
}) {
  return procurementRequest<ProcurementRequest>(
    "/api/procurement/requests",
    body,
  );
}

export function mutateProcurement(
  id: string,
  action: string,
  body: Record<string, unknown>,
) {
  return procurementRequest<ProcurementRequest>(
    `/api/procurement/requests/${encodeURIComponent(id)}/${action}`,
    body,
  );
}

export function expectedState(request: ProcurementRequest) {
  return {
    expected_state_version: request.state_version,
    expected_revision_id: request.current_revision_id,
    client_request_id: crypto.randomUUID(),
  };
}

export function procurementError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 423) {
      return "Оприходование пока отключено политикой безопасности.";
    }
    if (error.status === 409) {
      return "Заявка изменилась. Данные обновлены — проверьте действие ещё раз.";
    }
    if (error.status === 403) return "Недостаточно прав для этого действия.";
    return error.message;
  }
  return "Не удалось выполнить действие. Проверьте соединение.";
}
