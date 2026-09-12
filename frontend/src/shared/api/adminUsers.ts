import {
  ApiRequestError,
  type UserAccessStatus,
  type UserRole,
} from "./auth";

export type AdminUser = {
  id: string;
  telegram_user_id: number;
  username: string | null;
  first_name: string;
  last_name: string | null;
  role: UserRole;
  access_status: UserAccessStatus;
  created_at: string;
  updated_at: string;
  approved_at: string | null;
  is_recovery_identity: boolean;
};

export type AdminUserPage = {
  items: AdminUser[];
  total: number;
};

export type UserAccessEvent = {
  id: string;
  actor_user_id: string;
  actor_display_name: string;
  target_user_id: string;
  before_access_status: UserAccessStatus;
  after_access_status: UserAccessStatus;
  occurred_at: string;
};

export type UserAccessEventPage = {
  items: UserAccessEvent[];
  total: number;
};

export type UserRoleEvent = {
  id: string;
  actor_user_id: string;
  actor_display_name: string;
  target_user_id: string;
  before_role: UserRole;
  after_role: UserRole;
  occurred_at: string;
};

export type UserRoleEventPage = {
  items: UserRoleEvent[];
  total: number;
};

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let payload: unknown = null;

    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    let message = `HTTP ${response.status}`;
    let code: string | undefined;

    if (
      payload !== null
      && typeof payload === "object"
      && "detail" in payload
    ) {
      const detail = (
        payload as { detail?: unknown }
      ).detail;

      if (typeof detail === "string") {
        message = detail;
      } else if (
        detail !== null
        && typeof detail === "object"
      ) {
        const structured = detail as {
          code?: unknown;
          message?: unknown;
        };

        if (typeof structured.code === "string") {
          code = structured.code;
        }

        if (typeof structured.message === "string") {
          message = structured.message;
        }
      }
    }

    throw new ApiRequestError(
      response.status,
      message,
      code,
    );
  }

  return (await response.json()) as T;
}

export async function getAdminUsers(
  options: {
    query?: string;
    accessStatus?: UserAccessStatus;
    limit?: number;
    offset?: number;
  },
  signal?: AbortSignal,
): Promise<AdminUserPage> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 50),
    offset: String(options.offset ?? 0),
  });

  if (options.query) {
    params.set("q", options.query);
  }

  if (options.accessStatus) {
    params.set("access_status", options.accessStatus);
  }

  const response = await fetch(
    `/api/admin/users?${params.toString()}`,
    {
      credentials: "same-origin",
      signal,
    },
  );

  return readJson<AdminUserPage>(response);
}

export type AdminAccessRequestDecision =
  | "APPROVE"
  | "REJECT";

export async function decideAdminUserAccessRequest(
  userId: string,
  decision: AdminAccessRequestDecision,
): Promise<AdminUser> {
  const response = await fetch(
    `/api/admin/users/${encodeURIComponent(userId)}/access-request-decision`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ decision }),
    },
  );

  return readJson<AdminUser>(response);
}

export async function setAdminUserAccess(
  userId: string,
  accessStatus: UserAccessStatus,
): Promise<AdminUser> {
  const response = await fetch(
    `/api/admin/users/${encodeURIComponent(userId)}`,
    {
      method: "PATCH",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        access_status: accessStatus,
      }),
    },
  );

  return readJson<AdminUser>(response);
}

export async function setAdminUserRole(
  userId: string,
  role: UserRole,
): Promise<AdminUser> {
  const response = await fetch(
    `/api/admin/users/${encodeURIComponent(userId)}/role`,
    {
      method: "PATCH",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ role }),
    },
  );

  return readJson<AdminUser>(response);
}

export async function getUserAccessEvents(
  userId: string,
  options: {
    limit?: number;
    offset?: number;
  } = {},
  signal?: AbortSignal,
): Promise<UserAccessEventPage> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
    offset: String(options.offset ?? 0),
  });

  const response = await fetch(
    `/api/admin/users/${encodeURIComponent(userId)}/events?${params.toString()}`,
    {
      credentials: "same-origin",
      signal,
    },
  );

  return readJson<UserAccessEventPage>(response);
}

export async function getUserRoleEvents(
  userId: string,
  options: {
    limit?: number;
    offset?: number;
  } = {},
  signal?: AbortSignal,
): Promise<UserRoleEventPage> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
    offset: String(options.offset ?? 0),
  });

  const response = await fetch(
    `/api/admin/users/${encodeURIComponent(userId)}/role-events?${params.toString()}`,
    {
      credentials: "same-origin",
      signal,
    },
  );

  return readJson<UserRoleEventPage>(response);
}

export function adminUserError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    switch (error.code) {
      case "admin_user_outstanding_custody":
        return "У пользователя есть невозвращённое оборудование. Сначала оформите возврат.";

      case "admin_user_recovery_invariant":
        return "Recovery OWNER нельзя изменить или заблокировать через обычное управление пользователями.";

      case "admin_user_invalid_access_transition":
        return "Для текущего статуса используйте обработку запроса доступа.";

      case "admin_user_invalid_role_transition":
        return "Эта смена роли недопустима.";

      case "admin_user_pending_access_request_not_found":
        return "Запрос доступа уже обработан или больше не существует.";

      case "admin_user_forbidden":
        return "Недостаточно прав для этой операции.";

      case "admin_user_not_found":
        return "Пользователь больше не существует.";
    }

    if (error.status === 403) {
      return "Недостаточно прав для этой операции.";
    }

    if (error.status === 409) {
      return "Операция запрещена текущими правилами ролей или доступа.";
    }

    if (error.status === 404) {
      return "Пользователь больше не существует.";
    }

    if (error.status === 422) {
      return "Изменение невозможно для текущего состояния пользователя.";
    }
  }

  return "Не удалось выполнить операцию. Обновите страницу и попробуйте ещё раз.";
}
