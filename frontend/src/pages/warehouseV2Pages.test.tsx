import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
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

import { ApplicationRoutes } from "../app/App";
import {
  AUTH_QUERY_KEY,
  type AuthState,
  type Capability,
  type UserRole,
} from "../shared/api/auth";
import type {
  CatalogItem,
  CategoryDetail,
  CategorySummary,
} from "../shared/api/catalog";

const family: CategorySummary = {
  id: "family-transceivers",
  key: "transceivers",
  display_name: "Трансиверы",
  description: "SFP, SFP+, SFP28, XFP и QSFP для Ethernet и Fibre Channel.",
  parent_id: null,
  sort_order: 10,
  is_system: true,
};

const leaf: CategoryDetail = {
  id: "leaf-transceiver-ethernet",
  key: "transceiver_ethernet",
  display_name: "Ethernet",
  description: "Ethernet-трансиверы",
  parent_id: family.id,
  sort_order: 10,
  is_system: true,
  attributes: [
    {
      id: "attr-speed",
      key: "speed",
      label: "Скорость",
      data_type: "TEXT",
      unit: null,
      required: true,
      filterable: true,
      searchable: true,
      card_visible: true,
      detail_visible: true,
      table_visible: true,
      excel_visible: true,
      sort_order: 10,
      filter_type: "EXACT",
      allowed_values: null,
      validation_metadata: null,
      is_system: true,
    },
  ],
};

const item: CatalogItem = {
  id: "item-1",
  category: {
    id: leaf.id,
    key: leaf.key,
    display_name: leaf.display_name,
  },
  manufacturer: {
    id: "manufacturer-1",
    name: "Huawei",
  },
  name: "Huawei SFP-25G-SR",
  model: "SFP-25G-SR",
  status: "ACTIVE",
  archived_at: null,
  created_at: "2026-09-07T00:00:00Z",
  updated_at: "2026-09-07T00:00:00Z",
  attributes: {
    speed: "25 Гбит/с",
  },
};

const warehouse = {
  id: "location-warehouse",
  code: "SPK-WH",
  name: "Склад Spikatel",
  location_type: "WAREHOUSE" as const,
  address: "Тестовый адрес",
  status: "ACTIVE" as const,
};


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
      id: role === "ADMIN" ? "user-admin" : "user-vasya",
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
    headers: { "Content-Type": "application/json" },
  });
}

function renderRoute(path: string, role: UserRole) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Number.POSITIVE_INFINITY,
      },
      mutations: { retry: false },
    },
  });

  client.setQueryData(AUTH_QUERY_KEY, authState(role));

  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <ApplicationRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  return { ...view, client };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});


it("ENGINEER видит остаток и доступные складские операции", async () => {
  let movementBody: Record<string, unknown> | null = null;

  vi.stubGlobal("fetch", vi.fn(async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ) => {
    const url = String(input);

    if (url === "/api/catalog/items/item-1") {
      return jsonResponse(item);
    }

    if (url === `/api/catalog/categories/${leaf.key}`) {
      return jsonResponse(leaf);
    }

    if (url === "/api/inventory/items/item-1/summary") {
      return jsonResponse({
        total_count: 10,
        locations: [
          {
            id: "balance-1",
            item_id: item.id,
            item_name: item.name,
            quantity: 10,
            location: {
              location_id: warehouse.id,
              code: warehouse.code,
              name: warehouse.name,
            },
            updated_at: item.updated_at,
          },
        ],
      });
    }

    if (url === "/api/inventory/locations?limit=200&offset=0") {
      return jsonResponse({
        items: [warehouse],
        total: 1,
        limit: 200,
        offset: 0,
      });
    }

    if (url === "/api/inventory/movements") {
      movementBody = JSON.parse(String(init?.body)) as Record<string, unknown>;

      return jsonResponse({
        id: "movement-issue",
        journal_seq: 1,
        occurred_at: "2026-09-07T12:00:00Z",
        actor_user_id: "user-vasya",
        actor_display_name_snapshot: "Вася",
        movement_type: "ISSUE",
        source_location_name_snapshot: warehouse.name,
        destination_location_name_snapshot: null,
        lines: [
          {
            id: "line-1",
            item_id: item.id,
            item_name_snapshot: item.name,
            quantity: 4,
          },
        ],
      }, 201);
    }

    throw new Error(`unexpected fetch ${url}`);
  }));

  renderRoute("/catalog/items/item-1", "ENGINEER");

  expect(
    await screen.findByRole("heading", { name: "SFP-25G-SR" }),
  ).toBeInTheDocument();

  expect(
    await screen.findByText("В наличии: 10"),
  ).toBeInTheDocument();

  expect(screen.getByText(warehouse.name)).toBeInTheDocument();

  expect(
    screen.queryByText(/У пользователей/),
  ).not.toBeInTheDocument();

  expect(
    screen.queryByText(/на руках/i),
  ).not.toBeInTheDocument();

  expect(
    screen.getByRole("button", { name: "Переместить" }),
  ).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("button", { name: "Взять" }),
  );

  fireEvent.change(
    screen.getByLabelText("Количество"),
    { target: { value: "4" } },
  );

  fireEvent.click(
    screen.getByRole("button", { name: "Подтвердить" }),
  );

  await waitFor(() => {
    expect(movementBody).toMatchObject({
      movement_type: "ISSUE",
      source_location_id: warehouse.id,
      lines: [
        {
          item_id: item.id,
          quantity: 4,
        },
      ],
    });
  });

  expect(
    movementBody,
  ).not.toHaveProperty("holder_user_id");
});


it("RETURN показывает понятную ошибку при недостаточном custody", async () => {
  let movementBody: Record<string, unknown> | null = null;

  vi.stubGlobal("fetch", vi.fn(async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ) => {
    const url = String(input);

    if (url === "/api/catalog/items/item-1") {
      return jsonResponse(item);
    }

    if (url === `/api/catalog/categories/${leaf.key}`) {
      return jsonResponse(leaf);
    }

    if (url === "/api/inventory/items/item-1/summary") {
      return jsonResponse({
        total_count: 0,
        locations: [],
      });
    }

    if (url === "/api/inventory/locations?limit=200&offset=0") {
      return jsonResponse({
        items: [warehouse],
        total: 1,
        limit: 200,
        offset: 0,
      });
    }

    if (url === "/api/inventory/movements") {
      movementBody = JSON.parse(String(init?.body)) as Record<string, unknown>;

      return jsonResponse({
        detail: {
          code: "insufficient_custody",
          message: "insufficient user custody",
        },
      }, 409);
    }

    throw new Error(`unexpected fetch ${url}`);
  }));

  renderRoute("/catalog/items/item-1", "ENGINEER");

  await screen.findByRole(
    "heading",
    { name: "SFP-25G-SR" },
  );

  expect(
    await screen.findByText("В наличии: 0"),
  ).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("button", { name: "Вернуть" }),
  );

  fireEvent.change(
    screen.getByLabelText("Количество"),
    { target: { value: "16" } },
  );

  fireEvent.click(
    screen.getByRole("button", { name: "Подтвердить" }),
  );

  await waitFor(() => {
    expect(movementBody).toMatchObject({
      movement_type: "RETURN",
      destination_location_id: warehouse.id,
      lines: [
        {
          item_id: item.id,
          quantity: 16,
        },
      ],
    });
  });

  expect(
    movementBody,
  ).not.toHaveProperty("source_location_id");

  expect(
    movementBody,
  ).not.toHaveProperty("holder_user_id");

  expect(
    await screen.findByRole("alert"),
  ).toHaveTextContent(
    "Нельзя вернуть больше оборудования, чем числится за вами.",
  );
});


it("ADMIN управляет местами хранения без выдуманных адресов", async () => {
  let createBody: Record<string, unknown> | null = null;

  vi.stubGlobal("fetch", vi.fn(async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ) => {
    const url = String(input);

    if (url === "/api/inventory/locations?limit=200&offset=0") {
      return jsonResponse({
        items: [warehouse],
        total: 1,
        limit: 200,
        offset: 0,
      });
    }

    if (url === "/api/admin/inventory/locations") {
      createBody = JSON.parse(String(init?.body)) as Record<string, unknown>;

      return jsonResponse({
        id: "location-datapro",
        code: "DC-DATAPRO",
        name: "ЦОД DataPro",
        location_type: "DATACENTER",
        address: "Москва, тестовый адрес",
        status: "ACTIVE",
      }, 201);
    }

    throw new Error(`unexpected fetch ${url}`);
  }));

  renderRoute("/more/locations", "ADMIN");

  expect(
    await screen.findByRole(
      "heading",
      { name: warehouse.name },
    ),
  ).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole(
      "button",
      { name: "Добавить место хранения" },
    ),
  );

  expect(
    screen.getByRole(
      "dialog",
      { name: "Новое место хранения" },
    ),
  ).toBeInTheDocument();

  expect(
    screen.getByRole(
      "button",
      { name: "Закрыть редактор места хранения" },
    ),
  ).toBeInTheDocument();

  fireEvent.change(
    screen.getByLabelText("Код"),
    { target: { value: "DC-DATAPRO" } },
  );

  fireEvent.change(
    screen.getByLabelText("Название"),
    { target: { value: "ЦОД DataPro" } },
  );

  fireEvent.change(
    screen.getByLabelText("Тип"),
    { target: { value: "DATACENTER" } },
  );

  fireEvent.change(
    screen.getByLabelText("Адрес"),
    { target: { value: "Москва, тестовый адрес" } },
  );

  fireEvent.click(
    screen.getByRole("button", { name: "Сохранить" }),
  );

  await waitFor(() => {
    expect(createBody).toEqual({
      code: "DC-DATAPRO",
      name: "ЦОД DataPro",
      location_type: "DATACENTER",
      address: "Москва, тестовый адрес",
    });
  });
});


it("Locations снимает scroll lock при потере роли ADMIN", async () => {
  vi.stubGlobal("fetch", vi.fn(async (
    input: RequestInfo | URL,
  ) => {
    const url = String(input);

    if (
      url
      === "/api/inventory/locations?limit=200&offset=0"
    ) {
      return jsonResponse({
        items: [warehouse],
        total: 1,
        limit: 200,
        offset: 0,
      });
    }

    throw new Error(
      `unexpected fetch ${url}`,
    );
  }));

  const { client } = renderRoute(
    "/more/locations",
    "ADMIN",
  );

  await screen.findByRole(
    "heading",
    { name: warehouse.name },
  );

  fireEvent.click(
    screen.getByRole(
      "button",
      { name: "Добавить место хранения" },
    ),
  );

  expect(
    screen.getByRole(
      "dialog",
      { name: "Новое место хранения" },
    ),
  ).toBeInTheDocument();

  await waitFor(() => {
    expect(
      document.body.style.overflow,
    ).toBe("hidden");
  });

  act(() => {
    client.setQueryData(
      AUTH_QUERY_KEY,
      authState("ENGINEER"),
    );
  });

  await waitFor(() => {
    expect(
      screen.queryByRole(
        "dialog",
        { name: "Новое место хранения" },
      ),
    ).not.toBeInTheDocument();
  });

  await waitFor(() => {
    expect(
      document.body.style.overflow,
    ).toBe("");
  });

  act(() => {
    client.setQueryData(
      AUTH_QUERY_KEY,
      authState("ADMIN"),
    );
  });

  await waitFor(() => {
    expect(
      screen.queryByRole(
        "dialog",
        { name: "Новое место хранения" },
      ),
    ).not.toBeInTheDocument();
  });
});


it("Движения по умолчанию показывают 3 месяца и поддерживают нужные срезы", async () => {
  const movementRequests: string[] = [];

  vi.stubGlobal("fetch", vi.fn(async (
    input: RequestInfo | URL,
  ) => {
    const url = String(input);

    if (url === "/api/catalog/categories") {
      return jsonResponse([
        family,
        leaf,
      ]);
    }

    if (url === "/api/inventory/locations?limit=200&offset=0") {
      return jsonResponse({
        items: [warehouse],
        total: 1,
        limit: 200,
        offset: 0,
      });
    }

    if (url === "/api/inventory/movement-actors") {
      return jsonResponse([
        {
          id: "user-vasya",
          name: "Вася",
        },
      ]);
    }

    if (url.startsWith("/api/inventory/movements/feed?")) {
      movementRequests.push(url);

      return jsonResponse({
        items: [
          {
            id: "movement-1",
            journal_seq: 1,
            occurred_at: "2026-09-07T12:00:00Z",
            actor_user_id: "user-vasya",
            actor_display_name_snapshot: "Вася",
            movement_type: "ISSUE",
            source_location_name_snapshot: warehouse.name,
            destination_location_name_snapshot: null,
            lines: [
              {
                id: "line-1",
                item_id: item.id,
                item_name_snapshot: item.name,
                quantity: 4,
              },
            ],
          },
        ],
        limit: 30,
        cursor: url.includes("cursor=")
          ? "feed-page-2"
          : "feed-page-1",
        next_cursor: url.includes("cursor=")
          ? null
          : "feed-cursor-2",
        snapshot_at: "2026-09-09T07:00:00Z",
      });
    }

    throw new Error(`unexpected fetch ${url}`);
  }));

  renderRoute("/movements", "ADMIN");

  expect(
    await screen.findByText(/Huawei SFP-25G-SR/),
  ).toBeInTheDocument();

  await waitFor(() => {
    expect(
      movementRequests.some((url) => {
        const params = new URL(
          url,
          "http://test",
        ).searchParams;

        return params.get("period") === "3m"
          && params.get("limit") === "30"
          && params.get("offset") === null
          && params.get("cursor") === null;
      }),
    ).toBe(true);
  });

  fireEvent.click(screen.getByRole("button", { name: /Следующая страница/ }));
  await waitFor(() => {
    expect(movementRequests.some((url) => {
      const params = new URL(url, "http://test").searchParams;
      return params.get("cursor") === "feed-cursor-2"
        && params.get("snapshot_at") === null
        && params.get("before_journal_seq") === null;
    })).toBe(true);
  });

  fireEvent.change(
    screen.getByLabelText("Сотрудник"),
    { target: { value: "user-vasya" } },
  );

  fireEvent.change(
    screen.getByLabelText("Оборудование"),
    { target: { value: "long-range" } },
  );

  fireEvent.change(
    screen.getByLabelText("Место хранения"),
    { target: { value: warehouse.id } },
  );

  fireEvent.change(
    screen.getByLabelText("Период"),
    { target: { value: "30d" } },
  );

  await waitFor(() => {
    expect(
      movementRequests.some((url) => {
        const params = new URL(
          url,
          "http://test",
        ).searchParams;

        return params.get("period") === "30d"
          && params.get("actor_user_id") === "user-vasya"
          && params.get("category") === "transceivers"
          && params.get("long_range") === "true"
          && params.get("location_id") === warehouse.id;
      }),
    ).toBe(true);
  });
});
