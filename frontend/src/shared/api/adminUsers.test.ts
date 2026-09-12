import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import {
  adminUserError,
  setAdminUserAccess,
} from "./adminUsers";
import { ApiRequestError } from "./auth";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it(
  "preserves structured admin error code and maps custody conflict",
  async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            detail: {
              code: "admin_user_outstanding_custody",
              message: "synthetic backend detail",
            },
          }),
          {
            status: 409,
            headers: {
              "Content-Type": "application/json",
            },
          },
        ),
      ),
    );

    let caught: unknown;

    try {
      await setAdminUserAccess(
        "synthetic-user",
        "BLOCKED",
      );
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(
      ApiRequestError,
    );

    const requestError =
      caught as ApiRequestError;

    expect(requestError.code).toBe(
      "admin_user_outstanding_custody",
    );

    expect(adminUserError(requestError)).toBe(
      "У пользователя есть невозвращённое оборудование. Сначала оформите возврат.",
    );
  },
);
