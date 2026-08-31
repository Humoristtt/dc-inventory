export type UserRole = "USER" | "ADMIN";
export type UserAccessStatus =
  | "PENDING"
  | "APPROVED"
  | "REJECTED"
  | "BLOCKED";

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
  access_status: UserAccessStatus;
};

export type AuthState = {
  user: AuthUser;
  support: SupportContact;
};

export class ApiRequestError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiRequestError(response.status, `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function getAuthState(signal?: AbortSignal): Promise<AuthState> {
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
