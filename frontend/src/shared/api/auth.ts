export type UserRole =
  | "ENGINEER"
  | "SENIOR_ENGINEER"
  | "MANAGER"
  | "ADMIN"
  | "OWNER";

export type Capability =
  | "catalog.read"
  | "catalog.manage"
  | "catalog.archive"
  | "catalog.delete_unused"
  | "inventory.read"
  | "inventory.operate"
  | "inventory.admin"
  | "movement.read_own"
  | "movement.read_all"
  | "procurement.read"
  | "procurement.create"
  | "procurement.manage"
  | "procurement.accept"
  | "access.manage_users"
  | "access.assign_standard_roles"
  | "access.assign_admin";

export type UserAccessStatus =
  | "PENDING"
  | "APPROVED"
  | "REJECTED"
  | "BLOCKED";

export const ROLE_LABELS: Record<UserRole, string> = {
  ENGINEER: "Инженер",
  SENIOR_ENGINEER: "Старший инженер",
  MANAGER: "Менеджер",
  ADMIN: "Администратор",
  OWNER: "Владелец",
};

export type SupportContact = {
  username: string;
  url: string;
};

export type AuthUser = {
  id: string;
  telegram_user_id: number;
  username: string | null;
  first_name: string;
  last_name: string | null;
  role: UserRole;
  capabilities: Capability[];
  access_status: UserAccessStatus;
};

export type AuthState = {
  user: AuthUser;
  support: SupportContact;
};

export function hasCapability(
  user: Pick<AuthUser, "capabilities"> | null | undefined,
  capability: Capability,
): boolean {
  return user?.capabilities.includes(capability) ?? false;
}

export function hasAnyCapability(
  user: Pick<AuthUser, "capabilities"> | null | undefined,
  capabilities: readonly Capability[],
): boolean {
  return capabilities.some((capability) =>
    hasCapability(user, capability),
  );
}

export const AUTH_QUERY_KEY = ["auth", "state"] as const;

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string | undefined;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
  }
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiRequestError(response.status, `HTTP ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function getAuthState(
  signal?: AbortSignal,
): Promise<AuthState> {
  const response = await fetch("/api/auth/me", {
    credentials: "same-origin",
    signal,
  });

  return readJson<AuthState>(response);
}

export async function authenticateWithTelegram(
  initData: string,
  signal?: AbortSignal,
): Promise<AuthState> {
  const response = await fetch("/api/auth/telegram", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ init_data: initData }),
    signal,
  });

  return readJson<AuthState>(response);
}
