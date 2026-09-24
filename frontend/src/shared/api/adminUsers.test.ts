import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import {
  adminUserError,
  resetAdminUserAccount,
  resetAdminUserError,
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


it(
  "uses the shared API layer for account reset and accepts 204",
  async () => {
    const fetchMock = vi.fn(
      async (
        input: RequestInfo | URL,
        init?: RequestInit,
      ) => {
        expect(String(input)).toBe(
          "/api/admin/users/synthetic-user/reset",
        );

        expect(init?.method).toBe("POST");
        expect(init?.credentials).toBe("same-origin");

        expect(
          JSON.parse(String(init?.body)),
        ).toEqual({
          telegram_user_id: 424242,
          confirmation: "СБРОСИТЬ",
        });

        return new Response(null, {
          status: 204,
        });
      },
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      resetAdminUserAccount(
        "synthetic-user",
        424242,
        "СБРОСИТЬ",
      ),
    ).resolves.toBeUndefined();

    expect(fetchMock).toHaveBeenCalledTimes(1);
  },
);

it(
  "preserves reset error code in the shared API layer",
  async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            detail: {
              code: "admin_user_active_procurement",
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
      await resetAdminUserAccount(
        "synthetic-user",
        424242,
        "СБРОСИТЬ",
      );
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(
      ApiRequestError,
    );

    expect(
      resetAdminUserError(caught),
    ).toBe(
      "У пользователя есть незавершённая закупка. Завершите её или переназначьте ответственного.",
    );
  },
);
