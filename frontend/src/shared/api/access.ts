import { ApiRequestError, type UserAccessStatus } from "./auth";

export type AccessRequestStatus = "PENDING" | "APPROVED" | "REJECTED";

export type AccessRequest = {
  id: string;
  status: AccessRequestStatus;
  requested_at: string;
};

export type AccessState = {
  access_status: UserAccessStatus;
  request: AccessRequest | null;
};

async function readAccessState(response: Response): Promise<AccessState> {
  if (!response.ok) {
    throw new ApiRequestError(response.status, `HTTP ${response.status}`);
  }
  return (await response.json()) as AccessState;
}

export async function getAccessState(signal?: AbortSignal): Promise<AccessState> {
  const response = await fetch("/api/access-requests/me", {
    credentials: "same-origin",
    signal,
  });
  return readAccessState(response);
}

export async function requestAccess(): Promise<AccessState> {
  const response = await fetch("/api/access-requests", {
    method: "POST",
    credentials: "same-origin",
  });
  return readAccessState(response);
}
