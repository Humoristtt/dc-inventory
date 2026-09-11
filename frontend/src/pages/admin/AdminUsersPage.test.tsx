import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import { ApplicationRoutes } from "../../app/App";
import {
  AUTH_QUERY_KEY,
  type AuthState,
  type Capability,
  type UserRole,
} from "../../shared/api/auth";


function testCapabilities(role: UserRole): Capability[] {
  switch (role) {
    case "ENGINEER":
      return [
        "catalog.read",
        "inventory.read",
        "inventory.operate",
        "movement.read_own",
      ];
    case "SENIOR_ENGINEER":
      return [
        "catalog.read",
        "catalog.manage",
        "catalog.archive",
        "catalog.delete_unused",
        "inventory.read",
        "inventory.operate",
        "movement.read_own",
        "movement.read_all",
        "procurement.read",
        "procurement.accept",
      ];
    case "MANAGER":
      return [
        "catalog.read",
        "inventory.read",
        "procurement.read",
        "procurement.manage",
      ];
    case "ADMIN":
      return [
        "catalog.read",
        "catalog.manage",
        "catalog.archive",
        "catalog.delete_unused",
        "inventory.read",
        "inventory.operate",
        "inventory.admin",
        "movement.read_all",
        "procurement.read",
        "procurement.create",
        "procurement.accept",
        "access.manage_users",
        "access.assign_standard_roles",
      ];
    case "OWNER":
      return [
        "catalog.read",
        "catalog.manage",
        "catalog.archive",
        "catalog.delete_unused",
        "inventory.read",
        "inventory.operate",
        "inventory.admin",
        "movement.read_all",
        "procurement.read",
        "procurement.create",
        "procurement.accept",
        "access.manage_users",
        "access.assign_standard_roles",
        "access.assign_admin",
      ];
  }
}

function authState(role: UserRole): AuthState {
  return {
    user: {
      id: role === "ADMIN" ? "admin-1" : "user-1",
      telegram_user_id: role === "ADMIN" ? 1000 : 1001,
      username: role === "ADMIN" ? "admin" : "vasya",
      first_name: role === "ADMIN" ? "Администратор" : "Вася",
      last_name: null,
      role,
      capabilities: testCapabilities(role),
      access_status: "APPROVED",
    },
    support: {
      username: "support",
      url: "https://t.me/support",
    },
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
  });
}

function renderRoute(path: string, role: UserRole) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Number.POSITIVE_INFINITY,
      },
      mutations: {
        retry: false,
      },
    },
  });

  client.setQueryData(
    AUTH_QUERY_KEY,
    authState(role),
  );

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <ApplicationRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const managedUser = {
  id: "managed-user-1",
  telegram_user_id: 2001,
  username: "petrov",
  first_name: "Пётр",
  last_name: "Петров",
  role: "ENGINEER" as const,
  access_status: "APPROVED" as const,
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
  approved_at: "2026-09-01T10:00:00Z",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("ENGINEER не видит управление пользователями и не может открыть admin route", async () => {
  const fetchMock = vi.fn(async () => {
    throw new Error("USER must not call admin users API");
  });

  vi.stubGlobal("fetch", fetchMock);

  const view = renderRoute("/more", "ENGINEER");

  expect(
    await screen.findByRole("heading", { name: "Ещё" }),
  ).toBeInTheDocument();

  expect(
    screen.getByRole("link", { name: /Места хранения/ }),
  ).toBeInTheDocument();

  expect(
    screen.queryByRole("link", { name: /Пользователи/ }),
  ).not.toBeInTheDocument();

  view.unmount();

  renderRoute("/more/users", "ENGINEER");

  expect(
    await screen.findByRole("heading", { name: "Ещё" }),
  ).toBeInTheDocument();

  expect(
    screen.queryByRole("heading", { name: "Пользователи" }),
  ).not.toBeInTheDocument();

  expect(fetchMock).not.toHaveBeenCalled();
});

it("ADMIN видит раздел пользователей, блокирует пользователя и читает audit history", async () => {
  let currentStatus: "APPROVED" | "BLOCKED" = "APPROVED";
  let patchBody: unknown = null;

  const confirm = vi
    .spyOn(window, "confirm")
    .mockReturnValue(true);

  vi.stubGlobal(
    "fetch",
    vi.fn(async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const url = String(input);

      if (
        url.startsWith(
          "/api/admin/users?limit=200&offset=0",
        )
      ) {
        return jsonResponse({
          items: [
            {
              ...managedUser,
              access_status: currentStatus,
            },
          ],
          total: 1,
        });
      }

      if (
        url === "/api/admin/users/managed-user-1"
        && init?.method === "PATCH"
      ) {
        patchBody = JSON.parse(
          String(init.body),
        ) as unknown;

        currentStatus = "BLOCKED";

        return jsonResponse({
          ...managedUser,
          access_status: currentStatus,
          updated_at: "2026-09-09T12:00:00Z",
        });
      }

      if (
        url ===
        "/api/admin/users/managed-user-1/events?limit=100&offset=0"
      ) {
        return jsonResponse({
          items: [
            {
              id: "event-1",
              actor_user_id: "admin-1",
              target_user_id: "managed-user-1",
              before_access_status: "APPROVED",
              after_access_status: "BLOCKED",
              occurred_at: "2026-09-09T12:00:00Z",
            },
          ],
          total: 1,
        });
      }

      throw new Error(`unexpected fetch ${url}`);
    }),
  );

  const view = renderRoute("/more", "ADMIN");

  expect(
    await screen.findByRole("heading", { name: "Ещё" }),
  ).toBeInTheDocument();

  const usersLink = screen.getByRole(
    "link",
    { name: /Пользователи/ },
  );

  expect(usersLink).toBeInTheDocument();

  view.unmount();

  renderRoute("/more/users", "ADMIN");

  expect(
    await screen.findByRole(
      "heading",
      { name: "Пользователи" },
    ),
  ).toBeInTheDocument();

  expect(
    await screen.findByRole(
      "heading",
      { name: /Пётр Петров/ },
    ),
  ).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole(
      "button",
      { name: "Заблокировать" },
    ),
  );

  await waitFor(() => {
    expect(patchBody).toEqual({
      access_status: "BLOCKED",
    });
  });

  expect(confirm).toHaveBeenCalledTimes(1);

  await waitFor(() => {
    expect(
      screen.getByText("Заблокирован"),
    ).toBeInTheDocument();
  });

  fireEvent.click(
    screen.getByRole(
      "button",
      { name: "История изменений" },
    ),
  );

  expect(
    await screen.findByText(
      "Доступ разрешён → Заблокирован",
    ),
  ).toBeInTheDocument();

  expect(
    screen.getByText("Кем: admin-1"),
  ).toBeInTheDocument();
});

it("ADMIN может разблокировать заблокированного пользователя", async () => {
  let patchBody: unknown = null;

  vi.stubGlobal(
    "fetch",
    vi.fn(async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const url = String(input);

      if (
        url.startsWith(
          "/api/admin/users?limit=200&offset=0",
        )
      ) {
        return jsonResponse({
          items: [
            {
              ...managedUser,
              access_status: "BLOCKED",
            },
          ],
          total: 1,
        });
      }

      if (
        url === "/api/admin/users/managed-user-1"
        && init?.method === "PATCH"
      ) {
        patchBody = JSON.parse(
          String(init.body),
        ) as unknown;

        return jsonResponse({
          ...managedUser,
          access_status: "APPROVED",
          updated_at: "2026-09-09T12:10:00Z",
        });
      }

      throw new Error(`unexpected fetch ${url}`);
    }),
  );

  renderRoute("/more/users", "ADMIN");

  expect(
    await screen.findByText("Заблокирован"),
  ).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole(
      "button",
      { name: "Разблокировать" },
    ),
  );

  await waitFor(() => {
    expect(patchBody).toEqual({
      access_status: "APPROVED",
    });
  });
});
