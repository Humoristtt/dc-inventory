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
};

export type AdminUserPage = {
  items: AdminUser[];
  total: number;
};

export type UserAccessEvent = {
  id: string;
  actor_user_id: string;
  target_user_id: string;
  before_access_status: UserAccessStatus;
  after_access_status: UserAccessStatus;
  occurred_at: string;
};

export type UserAccessEventPage = {
  items: UserAccessEvent[];
  total: number;
};

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiRequestError(
      response.status,
      `HTTP ${response.status}`,
    );
  }

  return (await response.json()) as T;
}

export async function getAdminUsers(
  options: {
    query?: string;
    accessStatus?: UserAccessStatus;
  },
  signal?: AbortSignal,
): Promise<AdminUserPage> {
  const params = new URLSearchParams({
    limit: "200",
    offset: "0",
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

export async function getUserAccessEvents(
  userId: string,
  signal?: AbortSignal,
): Promise<UserAccessEventPage> {
  const response = await fetch(
    `/api/admin/users/${encodeURIComponent(userId)}/events?limit=100&offset=0`,
    {
      credentials: "same-origin",
      signal,
    },
  );

  return readJson<UserAccessEventPage>(response);
}

export function adminUserError(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 403) {
      return "Недостаточно прав для управления пользователями.";
    }

    if (error.status === 409) {
      return "Операция запрещена правилами управления доступом.";
    }

    if (error.status === 404) {
      return "Пользователь больше не существует.";
    }
  }

  return "Не удалось выполнить операцию. Обновите страницу и попробуйте ещё раз.";
}
