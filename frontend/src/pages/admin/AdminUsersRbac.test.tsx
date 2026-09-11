import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import { ApplicationRoutes } from "../../app/App";
import type { AdminUser } from "../../shared/api/adminUsers";
import {
  AUTH_QUERY_KEY,
  type AuthState,
  type Capability,
  type UserRole,
} from "../../shared/api/auth";

function capabilities(role: UserRole): Capability[] {
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
  const owner = role === "OWNER";

  return {
    user: {
      id: owner ? "actor-owner" : `actor-${role.toLowerCase()}`,
      telegram_user_id: owner ? 1000 : 1001,
      username: role.toLowerCase(),
      first_name: role,
      last_name: null,
      role,
      capabilities: capabilities(role),
      access_status: "APPROVED",
    },
    support: {
      username: "support",
      url: "https://t.me/support",
    },
  };
}

function makeUser(
  id: string,
  role: UserRole,
  accessStatus: AdminUser["access_status"] = "APPROVED",
): AdminUser {
  return {
    id,
    telegram_user_id: Number(id.replace(/\D/g, "")) || 2001,
    username: id,
    first_name: id,
    last_name: null,
    role,
    access_status: accessStatus,
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    approved_at:
      accessStatus === "APPROVED"
        ? "2026-09-01T10:00:00Z"
        : null,
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}

function installUsersApi(initialUsers: AdminUser[]) {
  const users = initialUsers.map((user) => ({ ...user }));
  const roleBodies: unknown[] = [];
  const accessBodies: unknown[] = [];

  const fetchMock = vi.fn(
    async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const url = String(input);

      if (url.startsWith("/api/admin/users?")) {
        return jsonResponse({
          items: users,
          total: users.length,
        });
      }

      const roleMatch = url.match(
        /^\/api\/admin\/users\/([^/]+)\/role$/,
      );

      if (roleMatch && init?.method === "PATCH") {
        const body = JSON.parse(
          String(init.body),
        ) as { role: UserRole };

        roleBodies.push(body);

        const id = decodeURIComponent(roleMatch[1]);
        const user = users.find((item) => item.id === id);

        if (!user) {
          return jsonResponse({}, 404);
        }

        user.role = body.role;
        user.updated_at = "2026-09-11T20:00:00Z";

        return jsonResponse(user);
      }

      const accessMatch = url.match(
        /^\/api\/admin\/users\/([^/]+)$/,
      );

      if (accessMatch && init?.method === "PATCH") {
        const body = JSON.parse(
          String(init.body),
        ) as {
          access_status: AdminUser["access_status"];
        };

        accessBodies.push(body);

        const id = decodeURIComponent(accessMatch[1]);
        const user = users.find((item) => item.id === id);

        if (!user) {
          return jsonResponse({}, 404);
        }

        user.access_status = body.access_status;
        user.approved_at =
          body.access_status === "APPROVED"
            ? "2026-09-11T20:00:00Z"
            : null;
        user.updated_at = "2026-09-11T20:00:00Z";

        return jsonResponse(user);
      }

      if (
        url.includes("/events?")
        || url.includes("/role-events?")
      ) {
        return jsonResponse({
          items: [],
          total: 0,
        });
      }

      throw new Error(`unexpected fetch ${url}`);
    },
  );

  vi.stubGlobal("fetch", fetchMock);

  return {
    fetchMock,
    roleBodies,
    accessBodies,
  };
}

function renderRoute(
  path: string,
  role: UserRole,
) {
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

function userCard(name: RegExp) {
  const heading = screen.getByRole(
    "heading",
    { name },
  );

  const card = heading.closest("section");

  if (!card) {
    throw new Error("user card not found");
  }

  return within(card);
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it.each([
  "SENIOR_ENGINEER",
  "MANAGER",
] as const)(
  "%s не получает управление пользователями",
  async (role) => {
    const fetchMock = vi.fn(async () => {
      throw new Error(
        `${role} must not call admin users API`,
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    renderRoute("/more/users", role);

    expect(
      await screen.findByRole(
        "heading",
        { name: "Ещё" },
      ),
    ).toBeInTheDocument();

    expect(
      screen.queryByRole(
        "heading",
        { name: "Пользователи" },
      ),
    ).not.toBeInTheDocument();

    expect(fetchMock).not.toHaveBeenCalled();
  },
);

it(
  "ADMIN меняет стандартную роль и не может назначить ADMIN",
  async () => {
    const api = installUsersApi([
      makeUser("engineer-2001", "ENGINEER"),
    ]);

    renderRoute("/more/users", "ADMIN");

    expect(
      await screen.findByRole(
        "heading",
        { name: /engineer-2001/ },
      ),
    ).toBeInTheDocument();

    const card = userCard(/engineer-2001/);
    const select = card.getByRole(
      "combobox",
      { name: "Роль пользователя" },
    );

    expect(
      within(select).getByRole(
        "option",
        { name: "Инженер" },
      ),
    ).toBeInTheDocument();

    expect(
      within(select).getByRole(
        "option",
        { name: "Старший инженер" },
      ),
    ).toBeInTheDocument();

    expect(
      within(select).getByRole(
        "option",
        { name: "Менеджер" },
      ),
    ).toBeInTheDocument();

    expect(
      within(select).queryByRole(
        "option",
        { name: "Администратор" },
      ),
    ).not.toBeInTheDocument();

    fireEvent.change(select, {
      target: {
        value: "MANAGER",
      },
    });

    await waitFor(() => {
      expect(api.roleBodies).toEqual([
        {
          role: "MANAGER",
        },
      ]);
    });
  },
);

it(
  "ADMIN не может менять роль или отключать другого ADMIN",
  async () => {
    installUsersApi([
      makeUser("other-admin", "ADMIN"),
    ]);

    renderRoute("/more/users", "ADMIN");

    expect(
      await screen.findByRole(
        "heading",
        { name: /other-admin/ },
      ),
    ).toBeInTheDocument();

    const card = userCard(/other-admin/);

    expect(
      card.queryByRole(
        "combobox",
        { name: "Роль пользователя" },
      ),
    ).not.toBeInTheDocument();

    expect(
      card.queryByRole(
        "button",
        { name: "Заблокировать" },
      ),
    ).not.toBeInTheDocument();

    expect(
      card.queryByRole(
        "button",
        { name: "Разблокировать" },
      ),
    ).not.toBeInTheDocument();
  },
);

it(
  "OWNER может назначить ADMIN и затем отключить ADMIN",
  async () => {
    const confirm = vi
      .spyOn(window, "confirm")
      .mockReturnValue(true);

    const api = installUsersApi([
      makeUser("engineer-2002", "ENGINEER"),
    ]);

    renderRoute("/more/users", "OWNER");

    expect(
      await screen.findByRole(
        "heading",
        { name: /engineer-2002/ },
      ),
    ).toBeInTheDocument();

    let card = userCard(/engineer-2002/);
    const select = card.getByRole(
      "combobox",
      { name: "Роль пользователя" },
    );

    expect(
      within(select).getByRole(
        "option",
        { name: "Администратор" },
      ),
    ).toBeInTheDocument();

    fireEvent.change(select, {
      target: {
        value: "ADMIN",
      },
    });

    await waitFor(() => {
      expect(api.roleBodies).toEqual([
        {
          role: "ADMIN",
        },
      ]);
    });

    await waitFor(() => {
      card = userCard(/engineer-2002/);

      expect(
        card.getByText(/Роль:\s*Администратор/),
      ).toBeInTheDocument();
    });

    fireEvent.click(
      card.getByRole(
        "button",
        { name: "Заблокировать" },
      ),
    );

    await waitFor(() => {
      expect(api.accessBodies).toEqual([
        {
          access_status: "BLOCKED",
        },
      ]);
    });

    expect(confirm).toHaveBeenCalledTimes(1);
  },
);

it(
  "OWNER не может изменить роль или отключить самого себя",
  async () => {
    installUsersApi([
      makeUser("actor-owner", "OWNER"),
    ]);

    renderRoute("/more/users", "OWNER");

    expect(
      await screen.findByRole(
        "heading",
        { name: /actor-owner/ },
      ),
    ).toBeInTheDocument();

    const card = userCard(/actor-owner/);

    expect(
      card.queryByRole(
        "combobox",
        { name: "Роль пользователя" },
      ),
    ).not.toBeInTheDocument();

    expect(
      card.queryByRole(
        "button",
        { name: "Заблокировать" },
      ),
    ).not.toBeInTheDocument();

    expect(
      card.queryByRole(
        "button",
        { name: "Разблокировать" },
      ),
    ).not.toBeInTheDocument();
  },
);
