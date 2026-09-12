import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  MemoryRouter,
  Route,
  Routes,
} from "react-router-dom";
import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import {
  AUTH_QUERY_KEY,
  type AuthState,
  type Capability,
  type UserRole,
} from "../../shared/api/auth";
import type {
  ProcurementLine,
  ProcurementRequest,
} from "../../shared/api/procurement";
import { ProcurementDetailPage } from "./ProcurementDetailPage";
import { ProcurementListPage } from "./ProcurementListPage";

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
  return {
    user: {
      id: `user-${role.toLowerCase()}`,
      telegram_user_id: 1001,
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

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}

function makeClient() {
  return new QueryClient({
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
}

function renderList(auth?: AuthState) {
  const client = makeClient();

  if (auth) {
    client.setQueryData(AUTH_QUERY_KEY, auth);
  }

  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/procurement"]}>
        <Routes>
          <Route
            path="/procurement"
            element={<ProcurementListPage />}
          />
          <Route
            path="/catalog"
            element={<p>CATALOG_DESTINATION</p>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  return { ...view, client };
}

function renderDetail(auth?: AuthState) {
  const client = makeClient();

  if (auth) {
    client.setQueryData(AUTH_QUERY_KEY, auth);
  }

  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/procurement/request-1"]}>
        <Routes>
          <Route
            path="/procurement/:requestId"
            element={<ProcurementDetailPage />}
          />
          <Route
            path="/catalog"
            element={<p>CATALOG_DESTINATION</p>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  return { ...view, client };
}

const existingLine: ProcurementLine = {
  id: "line-1",
  line_no: 1,
  line_type: "EXISTING_ITEM",
  catalog_item_id: "item-1",
  bound_item_id: "item-1",
  display_snapshot: {
    manufacturer_name: "Huawei",
    name: "SFP-25G-SR",
    model: "SFP-25G-SR",
  },
  quantity: 4,
};

const proposedUnboundLine: ProcurementLine = {
  id: "line-2",
  line_no: 1,
  line_type: "PROPOSED_ITEM",
  catalog_item_id: null,
  bound_item_id: null,
  display_snapshot: {
    manufacturer_name: "Generic",
    name: "Новый трансивер",
    model: "NEW-25G",
    category_key: "transceiver_ethernet",
    attributes: {},
  },
  quantity: 2,
};

function procurementRequest(
  overrides: Partial<ProcurementRequest> = {},
  line: ProcurementLine = existingLine,
): ProcurementRequest {
  const revision = {
    id: "revision-1",
    revision_number: 1,
    submitted_by: {
      id: "user-admin",
      display_name: "Администратор",
    },
    general_comment: null,
    created_at: "2026-09-12T10:00:00Z",
    lines: [line],
  };

  return {
    id: "request-1",
    request_number: "PR-2026-0001",
    status: "AWAITING_ACCEPTANCE",
    status_label: "Ожидает приёмки",
    initiator: {
      id: "user-admin",
      display_name: "Администратор",
    },
    assigned_manager: {
      id: "user-manager",
      display_name: "Менеджер",
    },
    current_revision_id: revision.id,
    revision_number: 1,
    line_count: 1,
    state_version: 7,
    created_at: "2026-09-12T10:00:00Z",
    updated_at: "2026-09-12T11:00:00Z",
    completed_at: null,
    current_revision: revision,
    revisions: [revision],
    events: [],
    final_movement_id: null,
    available_actions: [],
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("MANAGER после появления auth по умолчанию открывает очередь Мои", async () => {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL) => {
      const url = String(input);

      if (
        url
        === "/api/procurement/requests?view=my&limit=30&offset=0"
      ) {
        return jsonResponse({
          items: [],
          total: 0,
          limit: 30,
          offset: 0,
        });
      }

      throw new Error(`unexpected fetch ${url}`);
    },
  );

  vi.stubGlobal("fetch", fetchMock);

  const { client } = renderList();

  expect(
    fetchMock.mock.calls.some(
      ([input]) => String(input).includes("/api/procurement/"),
    ),
  ).toBe(false);

  act(() => {
    client.setQueryData(
      AUTH_QUERY_KEY,
      authState("MANAGER"),
    );
  });

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/procurement/requests?view=my&limit=30&offset=0",
      expect.anything(),
    );
  });

  expect(
    screen.getByRole("tab", { name: "Мои" })
      .getAttribute("aria-selected"),
  ).toBe("true");

  expect(
    fetchMock.mock.calls.some(
      ([input]) => String(input).includes("view=active"),
    ),
  ).toBe(false);
});

it("пользователь без procurement.manage начинает с Активные", async () => {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL) => {
      const url = String(input);

      if (
        url
        === "/api/procurement/requests?view=active&limit=30&offset=0"
      ) {
        return jsonResponse({
          items: [],
          total: 0,
          limit: 30,
          offset: 0,
        });
      }

      throw new Error(`unexpected fetch ${url}`);
    },
  );

  vi.stubGlobal("fetch", fetchMock);

  renderList(authState("SENIOR_ENGINEER"));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalled();
  });

  expect(
    screen.getByRole("tab", { name: "Активные" })
      .getAttribute("aria-selected"),
  ).toBe("true");

  expect(
    screen.queryByRole("tab", { name: "Мои" }),
  ).toBeNull();
});

it("ENGINEER без procurement.read уходит в каталог без Procurement API", async () => {
  const fetchMock = vi.fn(
    async (_input: RequestInfo | URL) => {
      throw new Error("fetch must not be called");
    },
  );

  vi.stubGlobal("fetch", fetchMock);

  renderList(authState("ENGINEER"));

  expect(
    await screen.findByText("CATALOG_DESTINATION"),
  ).toBeTruthy();

  expect(
    fetchMock.mock.calls.some(
      ([input]) => String(input).includes("/api/procurement/"),
    ),
  ).toBe(false);
});

it("detail не запрашивает заявку до готовности auth", async () => {
  const request = procurementRequest();

  const fetchMock = vi.fn(
    async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/procurement/requests/request-1") {
        return jsonResponse(request);
      }

      throw new Error(`unexpected fetch ${url}`);
    },
  );

  vi.stubGlobal("fetch", fetchMock);

  const { client } = renderDetail();

  expect(
    fetchMock.mock.calls.some(
      ([input]) =>
        String(input)
        === "/api/procurement/requests/request-1",
    ),
  ).toBe(false);

  act(() => {
    client.setQueryData(
      AUTH_QUERY_KEY,
      authState("SENIOR_ENGINEER"),
    );
  });

  expect(
    await screen.findByText("PR-2026-0001"),
  ).toBeTruthy();

  expect(
    fetchMock.mock.calls.filter(
      ([input]) =>
        String(input)
        === "/api/procurement/requests/request-1",
    ),
  ).toHaveLength(1);
});

it("detail показывает только действия из available_actions", async () => {
  const request = procurementRequest({
    available_actions: [
      "report_discrepancy",
      "complete_acceptance",
    ],
  });

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/procurement/requests/request-1") {
        return jsonResponse(request);
      }

      if (
        url
        === "/api/inventory/locations?limit=200&offset=0"
      ) {
        return jsonResponse({
          items: [],
          total: 0,
          limit: 200,
          offset: 0,
        });
      }

      throw new Error(`unexpected fetch ${url}`);
    }),
  );

  renderDetail(authState("SENIOR_ENGINEER"));

  expect(
    await screen.findByRole("button", {
      name: "Подтвердить приёмку",
    }),
  ).toBeTruthy();

  expect(
    screen.getByRole("button", {
      name: "Есть расхождения",
    }),
  ).toBeTruthy();

  expect(
    screen.queryByRole("button", {
      name: "Взять на себя",
    }),
  ).toBeNull();

  expect(
    screen.queryByRole("button", {
      name: "Передать менеджеру",
    }),
  ).toBeNull();

  expect(
    screen.queryByRole("button", {
      name: "Принять в работу",
    }),
  ).toBeNull();

  expect(
    screen.queryByRole("button", {
      name: "Вернуть на корректировку",
    }),
  ).toBeNull();

  expect(
    screen.queryByRole("button", {
      name: "Передать на приёмку",
    }),
  ).toBeNull();

  expect(
    screen.queryByRole("button", {
      name: "Создать новую редакцию",
    }),
  ).toBeNull();
});

it("acceptance требует второй confirm, место и отправляет полный state contract", async () => {
  const request = procurementRequest({
    available_actions: ["complete_acceptance"],
  });

  const acceptanceBodies: Record<string, unknown>[] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn(async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const url = String(input);

      if (url === "/api/procurement/requests/request-1") {
        return jsonResponse(request);
      }

      if (
        url
        === "/api/inventory/locations?limit=200&offset=0"
      ) {
        return jsonResponse({
          items: [
            {
              id: "location-1",
              code: "WH-01",
              name: "Основной склад",
              location_type: "WAREHOUSE",
              address: null,
              status: "ACTIVE",
            },
          ],
          total: 1,
          limit: 200,
          offset: 0,
        });
      }

      if (
        url
        === "/api/procurement/requests/request-1/acceptance"
        && init?.method === "POST"
      ) {
        acceptanceBodies.push(
          JSON.parse(
            String(init.body),
          ) as Record<string, unknown>,
        );

        return jsonResponse(
          procurementRequest({
            status: "COMPLETED",
            status_label: "Завершена",
            state_version: 8,
            final_movement_id: "movement-1",
            completed_at: "2026-09-12T12:00:00Z",
            available_actions: [],
          }),
        );
      }

      throw new Error(`unexpected fetch ${url}`);
    }),
  );

  renderDetail(authState("SENIOR_ENGINEER"));

  const opener = await screen.findByRole("button", {
    name: "Подтвердить приёмку",
  });

  fireEvent.click(opener);

  const dialog = screen.getByRole("dialog", {
    name: "Подтвердить приёмку",
  });

  expect(
    dialog.textContent?.includes("SFP-25G-SR"),
  ).toBe(true);

  expect(
    dialog.textContent?.includes("4 шт."),
  ).toBe(true);

  const confirm = screen.getByRole("button", {
    name: "Подтвердить и оприходовать",
  }) as HTMLButtonElement;

  expect(confirm.disabled).toBe(true);

  fireEvent.change(
    screen.getByLabelText("Место приёмки"),
    {
      target: {
        value: "location-1",
      },
    },
  );

  expect(confirm.disabled).toBe(false);

  fireEvent.click(confirm);

  await waitFor(() => {
    expect(acceptanceBodies).toHaveLength(1);
  });

  const acceptanceBody = acceptanceBodies[0];

  expect(acceptanceBody).toBeDefined();

  if (!acceptanceBody) {
    throw new Error("acceptance request body was not captured");
  }

  expect(acceptanceBody).toMatchObject({
    expected_state_version: 7,
    expected_revision_id: "revision-1",
    receiving_location_id: "location-1",
  });

  expect(
    typeof acceptanceBody.client_request_id,
  ).toBe("string");
});

it("несвязанная proposed-позиция блокирует оприходование", async () => {
  const request = procurementRequest(
    {
      available_actions: ["complete_acceptance"],
    },
    proposedUnboundLine,
  );

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/procurement/requests/request-1") {
        return jsonResponse(request);
      }

      if (
        url
        === "/api/inventory/locations?limit=200&offset=0"
      ) {
        return jsonResponse({
          items: [
            {
              id: "location-1",
              code: "WH-01",
              name: "Основной склад",
              location_type: "WAREHOUSE",
              address: null,
              status: "ACTIVE",
            },
          ],
          total: 1,
          limit: 200,
          offset: 0,
        });
      }

      throw new Error(`unexpected fetch ${url}`);
    }),
  );

  renderDetail(authState("SENIOR_ENGINEER"));

  fireEvent.click(
    await screen.findByRole("button", {
      name: "Подтвердить приёмку",
    }),
  );

  fireEvent.change(
    screen.getByLabelText("Место приёмки"),
    {
      target: {
        value: "location-1",
      },
    },
  );

  const confirm = screen.getByRole("button", {
    name: "Подтвердить и оприходовать",
  }) as HTMLButtonElement;

  expect(confirm.disabled).toBe(true);
});

it("dialog удерживает фокус, закрывается Escape и возвращает фокус opener", async () => {
  const request = procurementRequest({
    available_actions: ["report_discrepancy"],
  });

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/procurement/requests/request-1") {
        return jsonResponse(request);
      }

      throw new Error(`unexpected fetch ${url}`);
    }),
  );

  renderDetail(authState("SENIOR_ENGINEER"));

  const opener = await screen.findByRole("button", {
    name: "Есть расхождения",
  });

  opener.focus();
  fireEvent.click(opener);

  const dialog = screen.getByRole("dialog", {
    name: "Есть расхождения",
  });
  const close = screen.getByRole("button", {
    name: "Закрыть",
  });
  const textarea = screen.getByLabelText(
    "Что отличается",
  );

  await waitFor(() => {
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  expect(document.activeElement).toBe(close);

  fireEvent.keyDown(window, {
    key: "Tab",
    shiftKey: true,
  });

  expect(document.activeElement).toBe(textarea);

  fireEvent.keyDown(window, {
    key: "Tab",
  });

  expect(document.activeElement).toBe(close);

  fireEvent.keyDown(window, {
    key: "Escape",
  });

  await waitFor(() => {
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  expect(document.activeElement).toBe(opener);
});
