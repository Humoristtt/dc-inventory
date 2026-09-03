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

import { ApplicationRoutes } from "../app/App";
import {
  AUTH_QUERY_KEY,
  type AuthState,
} from "../shared/api/auth";
import type {
  CatalogItem,
  CategoryDetail,
} from "../shared/api/catalog";

const category: CategoryDetail = {
  id: "category-sfp",
  key: "sfp",
  display_name: "SFP-модули",
  description: "Оптические трансиверы",
  default_accounting_mode: "QUANTITY",
  sort_order: 10,
  is_system: true,
  attributes: [
    {
      id: "speed-profile",
      key: "speed_profile",
      label: "Профиль скорости",
      data_type: "TEXT",
      unit: null,
      required: false,
      filterable: false,
      searchable: true,
      card_visible: false,
      detail_visible: true,
      table_visible: true,
      excel_visible: true,
      sort_order: 15,
      filter_type: "NONE",
      allowed_values: null,
      validation_metadata: { max_length: 255, preserve_whitespace: true },
      is_system: true,
    },
    {
      id: "speed",
      key: "speed_mbps",
      label: "Скорость",
      data_type: "INTEGER",
      unit: "Mbps",
      required: true,
      filterable: true,
      searchable: true,
      card_visible: true,
      detail_visible: true,
      table_visible: true,
      excel_visible: true,
      sort_order: 20,
      filter_type: "RANGE",
      allowed_values: null,
      validation_metadata: { min: 1 },
      is_system: true,
    },
    {
      id: "connector",
      key: "connector",
      label: "Разъём",
      data_type: "ENUM",
      unit: null,
      required: false,
      filterable: true,
      searchable: true,
      card_visible: true,
      detail_visible: true,
      table_visible: true,
      excel_visible: true,
      sort_order: 60,
      filter_type: "EXACT",
      allowed_values: ["LC Duplex", "MPO", "MPO/PC"],
      validation_metadata: null,
      is_system: true,
    },
  ],
};

const activeItem: CatalogItem = {
  id: "item-1",
  category: { id: category.id, key: category.key, display_name: category.display_name },
  manufacturer: { id: "manufacturer-1", name: "Avago" },
  name: "Трансивер FC",
  model: "AFBR-57F5MZ-ELX",
  manufacturer_part_number: null,
  internal_code: null,
  description: null,
  accounting_mode: "QUANTITY",
  status: "ACTIVE",
  comment: null,
  datasheet_url: null,
  technical_data_source: null,
  archived_at: null,
  created_at: "2026-09-03T00:00:00Z",
  updated_at: "2026-09-03T00:00:00Z",
  attributes: {
    speed_profile: "4/8/16G FC",
    speed_mbps: 16000,
    connector: "LC Duplex",
  },
};

function authState(role: "USER" | "ADMIN"): AuthState {
  return {
    user: {
      id: "00000000-0000-4000-8000-000000000111",
      telegram_user_id: 1001,
      username: "telegram-name-must-not-be-used",
      first_name: "Иван",
      last_name: null,
      role,
      access_status: "APPROVED",
    },
    support: { username: "support", url: "https://t.me/support" },
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

function renderRoute(path: string, role: "USER" | "ADMIN") {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Number.POSITIVE_INFINITY },
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

it("ADMIN creates metadata-driven item after inline manufacturer and duplicate warning", async () => {
  let createPayload: Record<string, unknown> | null = null;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/catalog/categories") return jsonResponse([category]);
    if (url === "/api/catalog/categories/sfp") return jsonResponse(category);
    if (url.startsWith("/api/catalog/manufacturers?")) {
      return jsonResponse({ items: [], total: 0, limit: 200, offset: 0 });
    }
    if (url === "/api/admin/catalog/manufacturers") {
      return jsonResponse({
        id: "manufacturer-new",
        name: "D-WDM.RU",
        created_at: "2026-09-03T00:00:00Z",
        updated_at: "2026-09-03T00:00:00Z",
      }, 201);
    }
    if (url === "/api/admin/catalog/items/check-duplicates") {
      return jsonResponse({
        candidates: [{
          item_id: "candidate-1",
          name: "Похожий трансивер",
          model: "DSO-21-1D",
          manufacturer_id: "manufacturer-new",
          manufacturer_name: "D-WDM.RU",
          manufacturer_part_number: null,
          reason: "same_category_manufacturer_name_model",
        }],
      });
    }
    if (url === "/api/admin/catalog/items") {
      createPayload = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return jsonResponse({
        ...activeItem,
        id: "item-created",
        manufacturer: { id: "manufacturer-new", name: "D-WDM.RU" },
        name: "Трансивер 10/25G",
        model: "DSO-25",
        attributes: {
          speed_profile: "10/25 Гбит/с",
          speed_mbps: 25000,
          connector: "MPO/PC",
        },
      }, 201);
    }
    if (url.startsWith("/api/inventory/stock?")) {
      return jsonResponse({ items: [], total: 0, limit: 200, offset: 0 });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  const { client } = renderRoute("/catalog/new?category=sfp", "ADMIN");
  const facetKey = ["catalog", "facets", "f03-create"] as const;
  client.setQueryData(facetKey, { facets: [] });

  fireEvent.change(await screen.findByLabelText(/^Название/), {
    target: { value: "Трансивер 10/25G" },
  });
  fireEvent.change(screen.getByLabelText("Модель"), { target: { value: "DSO-25" } });
  fireEvent.change(screen.getByLabelText(/^Профиль скорости/), {
    target: { value: "10/25 Гбит/с" },
  });
  fireEvent.change(screen.getByLabelText(/^Скорость/), { target: { value: "25000" } });
  fireEvent.change(screen.getByLabelText("Разъём"), { target: { value: "MPO/PC" } });

  fireEvent.click(screen.getByRole("button", { name: "+ Новый" }));
  fireEvent.change(screen.getByLabelText("Название нового производителя"), {
    target: { value: "D-WDM.RU" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Создать" }));
  await waitFor(() => expect(screen.getByLabelText(/^Название/)).toHaveValue("Трансивер 10/25G"));
  expect(screen.getByLabelText("Производитель")).toHaveValue("manufacturer-new");

  fireEvent.click(screen.getByRole("button", { name: "Проверить и создать" }));
  expect(await screen.findByRole("heading", { name: "Похожие позиции уже есть" })).toBeInTheDocument();
  expect(screen.getByText("Совпадают категория, производитель, название и модель")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Всё равно создать" }));

  expect(await screen.findByText("Карточка оборудования")).toBeInTheDocument();
  expect(createPayload).toMatchObject({
    category_key: "sfp",
    manufacturer_id: "manufacturer-new",
    manufacturer_part_number: null,
    attributes: {
      speed_profile: "10/25 Гбит/с",
      speed_mbps: 25000,
      connector: "MPO/PC",
    },
  });
  expect(client.getQueryState(facetKey)?.isInvalidated).toBe(true);
});

it("ignores a stale duplicate-check response when the form changes in flight", async () => {
  const duplicateResponse = deferred<Response>();
  let duplicateChecks = 0;
  let createCalls = 0;

  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url === "/api/catalog/categories") return jsonResponse([category]);
    if (url === "/api/catalog/categories/sfp") return jsonResponse(category);
    if (url.startsWith("/api/catalog/manufacturers?")) {
      return jsonResponse({ items: [], total: 0, limit: 200, offset: 0 });
    }
    if (url === "/api/admin/catalog/items/check-duplicates") {
      duplicateChecks += 1;
      return duplicateResponse.promise;
    }
    if (url === "/api/admin/catalog/items") {
      createCalls += 1;
      return jsonResponse(activeItem, 201);
    }
    throw new Error(`unexpected fetch ${url}`);
  }));

  renderRoute("/catalog/new?category=sfp", "ADMIN");

  fireEvent.change(await screen.findByLabelText(/^Название/), {
    target: { value: "Позиция A" },
  });
  fireEvent.change(screen.getByLabelText("Модель"), {
    target: { value: "MODEL-A" },
  });
  fireEvent.change(screen.getByLabelText(/^Скорость/), {
    target: { value: "25000" },
  });

  fireEvent.click(screen.getByRole("button", { name: "Проверить и создать" }));

  await waitFor(() => expect(duplicateChecks).toBe(1));

  fireEvent.change(screen.getByLabelText(/^Название/), {
    target: { value: "Позиция B" },
  });

  duplicateResponse.resolve(jsonResponse({
    candidates: [{
      item_id: "candidate-a",
      name: "Позиция A",
      model: "MODEL-A",
      manufacturer_id: null,
      manufacturer_name: null,
      manufacturer_part_number: null,
      reason: "same_category_manufacturer_name_model",
    }],
  }));

  expect(
    await screen.findByText(
      "Данные формы изменились во время проверки дублей. Проверьте их и повторите проверку.",
    ),
  ).toBeInTheDocument();

  expect(
    screen.queryByRole("heading", { name: "Похожие позиции уже есть" }),
  ).not.toBeInTheDocument();

  expect(createCalls).toBe(0);
});

it("invalidates duplicate review when catalog identity changes", async () => {
  let duplicateChecks = 0;
  let createCalls = 0;

  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url === "/api/catalog/categories") return jsonResponse([category]);
    if (url === "/api/catalog/categories/sfp") return jsonResponse(category);
    if (url.startsWith("/api/catalog/manufacturers?")) {
      return jsonResponse({ items: [], total: 0, limit: 200, offset: 0 });
    }
    if (url === "/api/admin/catalog/items/check-duplicates") {
      duplicateChecks += 1;
      return jsonResponse({
        candidates: [{
          item_id: `candidate-${duplicateChecks}`,
          name: duplicateChecks === 1 ? "Позиция A" : "Позиция B",
          model: duplicateChecks === 1 ? "MODEL-A" : "MODEL-B",
          manufacturer_id: null,
          manufacturer_name: null,
          manufacturer_part_number: null,
          reason: "same_category_manufacturer_name_model",
        }],
      });
    }
    if (url === "/api/admin/catalog/items") {
      createCalls += 1;
      return jsonResponse(activeItem, 201);
    }
    throw new Error(`unexpected fetch ${url}`);
  }));

  renderRoute("/catalog/new?category=sfp", "ADMIN");

  fireEvent.change(await screen.findByLabelText(/^Название/), {
    target: { value: "Позиция A" },
  });
  fireEvent.change(screen.getByLabelText("Модель"), {
    target: { value: "MODEL-A" },
  });
  fireEvent.change(screen.getByLabelText(/^Скорость/), {
    target: { value: "25000" },
  });

  fireEvent.click(screen.getByRole("button", { name: "Проверить и создать" }));

  expect(
    await screen.findByRole("heading", { name: "Похожие позиции уже есть" }),
  ).toBeInTheDocument();
  expect(duplicateChecks).toBe(1);

  fireEvent.change(screen.getByLabelText(/^Название/), {
    target: { value: "Позиция B" },
  });
  fireEvent.change(screen.getByLabelText("Модель"), {
    target: { value: "MODEL-B" },
  });

  expect(
    screen.queryByRole("heading", { name: "Похожие позиции уже есть" }),
  ).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Проверить и создать" }));

  await waitFor(() => expect(duplicateChecks).toBe(2));

  expect(
    await screen.findByRole("heading", { name: "Похожие позиции уже есть" }),
  ).toBeInTheDocument();

  expect(createCalls).toBe(0);
});

it("shows stock by location and custody and lets ADMIN archive without deleting stock", async () => {
  let item = activeItem;
  const stockRequests: string[] = [];

  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url === "/api/catalog/items/item-1") {
      return jsonResponse(item);
    }

    if (url === "/api/catalog/categories/sfp") {
      return jsonResponse(category);
    }

    if (url === "/api/inventory/items/item-1/summary") {
      return jsonResponse({
        available_count: 8,
        custody_count: 2,
        total_count: 10,
      });
    }

    if (url.startsWith("/api/inventory/stock?")) {
      stockRequests.push(url);

      const params = new URL(
        url,
        "http://test",
      ).searchParams;

      const offset = Number(params.get("offset") ?? "0");

      if (offset === 0) {
        return jsonResponse({
          items: [
            {
              id: "balance-location",
              item_id: item.id,
              item_name: item.name,
              quantity: 8,
              location: {
                location_id: "location-1",
                code: "A-01",
                name: "Основная стойка",
              },
              holder: null,
              updated_at: item.updated_at,
            },
          ],
          total: 2,
          limit: 50,
          offset: 0,
        });
      }

      if (offset === 1) {
        return jsonResponse({
          items: [
            {
              id: "balance-holder",
              item_id: item.id,
              item_name: item.name,
              quantity: 2,
              location: null,
              holder: {
                user_id: "user-2",
                display_name: "Пётр",
              },
              updated_at: item.updated_at,
            },
          ],
          total: 2,
          limit: 50,
          offset: 1,
        });
      }

      throw new Error(`unexpected stock offset ${offset}`);
    }

    if (url === "/api/admin/catalog/items/item-1/archive") {
      item = {
        ...item,
        status: "ARCHIVED",
        archived_at: "2026-09-03T01:00:00Z",
      };
      return jsonResponse(item);
    }

    throw new Error(`unexpected fetch ${url}`);
  }));

  const { client } = renderRoute("/catalog/items/item-1", "ADMIN");
  const facetKey = ["catalog", "facets", "f03-archive"] as const;
  client.setQueryData(facetKey, { facets: [] });

  expect(await screen.findByText("A-01")).toBeInTheDocument();
  expect(screen.getByText("Основная стойка")).toBeInTheDocument();

  expect(
    screen.getByText(
      "Выданные позиции есть — загрузите следующие позиции",
    ),
  ).toBeInTheDocument();

  expect(
    screen.queryByText("Пётр"),
  ).not.toBeInTheDocument();

  expect(
    screen.getByRole("link", { name: "Редактировать" }),
  ).toBeInTheDocument();

  const showMore = screen.getByRole(
    "button",
    { name: "Показать ещё позиции" },
  );

  expect(stockRequests).toHaveLength(1);

  const firstStockParams = new URL(
    stockRequests[0],
    "http://test",
  ).searchParams;

  expect(firstStockParams.get("limit")).toBe("50");
  expect(firstStockParams.get("offset")).toBe("0");

  fireEvent.click(showMore);

  expect(
    await screen.findByText("Пётр"),
  ).toBeInTheDocument();

  expect(stockRequests).toHaveLength(2);

  const secondStockParams = new URL(
    stockRequests[1],
    "http://test",
  ).searchParams;

  expect(secondStockParams.get("limit")).toBe("50");
  expect(secondStockParams.get("offset")).toBe("1");

  fireEvent.click(screen.getByRole("button", { name: "В архив" }));

  expect(
    screen.getByText(/Текущий складской остаток.*не удаляются/),
  ).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("button", { name: "Подтвердить" }),
  );

  expect(
    await screen.findByRole(
      "button",
      { name: "Вернуть из архива" },
    ),
  ).toBeInTheDocument();

  expect(
    client.getQueryState(facetKey)?.isInvalidated,
  ).toBe(true);
});

it("USER item detail hides redacted serial identity for another holder", async () => {
  const serialItem: CatalogItem = {
    ...activeItem,
    accounting_mode: "SERIAL",
  };

  const unitRequests: string[] = [];

  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url === "/api/catalog/items/item-1") {
      return jsonResponse(serialItem);
    }

    if (url === "/api/catalog/categories/sfp") {
      return jsonResponse(category);
    }

    if (url === "/api/inventory/items/item-1/summary") {
      return jsonResponse({
        available_count: 0,
        custody_count: 1,
        total_count: 1,
      });
    }

    if (url.startsWith("/api/inventory/units?")) {
      unitRequests.push(url);

      const params = new URL(
        url,
        "http://test",
      ).searchParams;

      if (params.get("state") === "STORED") {
        return jsonResponse({
          items: [],
          total: 0,
          limit: 50,
          offset: 0,
        });
      }

      if (params.get("state") === "ISSUED") {
        return jsonResponse({
          items: [
            {
              id: "foreign-unit",
              item_id: serialItem.id,
              item_name: serialItem.name,
              serial_number: null,
              wwn: null,
              comment: null,
              state: "ISSUED",
              location: null,
              holder: {
                user_id: null,
                display_name: "Сотрудник",
              },
              created_at: serialItem.created_at,
              updated_at: serialItem.updated_at,
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        });
      }
    }

    throw new Error(`unexpected fetch ${url}`);
  }));

  renderRoute("/catalog/items/item-1", "USER");

  expect(
    await screen.findByRole(
      "heading",
      { name: serialItem.model ?? serialItem.name },
    ),
  ).toBeInTheDocument();

  expect(
    await screen.findByText("Сотрудник"),
  ).toBeInTheDocument();

  expect(
    await screen.findByText("1 шт."),
  ).toBeInTheDocument();

  expect(unitRequests).toHaveLength(2);

  for (const request of unitRequests) {
    const params = new URL(
      request,
      "http://test",
    ).searchParams;

    expect(params.get("limit")).toBe("50");
    expect(params.get("offset")).toBe("0");
  }

  expect(
    screen.queryByText("SN null"),
  ).not.toBeInTheDocument();

  expect(
    screen.queryByText(/WWN/),
  ).not.toBeInTheDocument();

  expect(
    screen.queryByText("Управление позицией"),
  ).not.toBeInTheDocument();
});

it("USER sees own quantity and serial holdings without sending holder identity", async () => {
  const requestedUrls: string[] = [];

  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    requestedUrls.push(url);

    if (url.startsWith("/api/inventory/mine?")) {
      return jsonResponse({
        items: [
          {
            item_id: "quantity-item",
            item_name: "Патч-корд LC",
            accounting_mode: "QUANTITY",
            quantity: 4,
            serial_count: 0,
            serial_preview: [],
          },
          {
            item_id: "serial-item",
            item_name: "Сетевая карта",
            accounting_mode: "SERIAL",
            quantity: 0,
            serial_count: 1,
            serial_preview: [
              {
                id: "unit-1",
                serial_number: "SN-100",
                wwn: "10:00:00:00:00:01",
              },
            ],
          },
        ],
        total: 2,
        limit: 20,
        offset: 0,
      });
    }

    throw new Error(`unexpected fetch ${url}`);
  }));

  renderRoute("/mine", "USER");

  expect(
    await screen.findByRole(
      "heading",
      { name: "Патч-корд LC" },
    ),
  ).toBeInTheDocument();

  expect(
    screen.getByRole(
      "heading",
      { name: "Сетевая карта" },
    ),
  ).toBeInTheDocument();

  expect(
    screen.getByText("SN SN-100"),
  ).toBeInTheDocument();

  expect(
    screen.queryByText("Управление позицией"),
  ).not.toBeInTheDocument();

  const mineRequests = requestedUrls.filter(
    (url) => url.startsWith("/api/inventory/mine?"),
  );

  expect(mineRequests).toHaveLength(1);

  const params = new URL(
    mineRequests[0],
    "http://test",
  ).searchParams;

  expect(params.get("limit")).toBe("20");
  expect(params.get("offset")).toBe("0");
  expect(params.has("holder_user_id")).toBe(false);

  expect(
    mineRequests[0],
  ).not.toContain(authState("USER").user.id);

  expect(
    mineRequests[0],
  ).not.toContain("telegram-name-must-not-be-used");
});

it("My Equipment exposes empty and retry states", async () => {
  let failures = 1;

  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url.startsWith("/api/inventory/mine?")) {
      if (failures > 0) {
        failures -= 1;
        return jsonResponse(
          { detail: "failed" },
          500,
        );
      }

      return jsonResponse({
        items: [],
        total: 0,
        limit: 20,
        offset: 0,
      });
    }

    throw new Error(`unexpected fetch ${url}`);
  }));

  renderRoute("/mine", "USER");

  expect(
    await screen.findByText(
      "Не удалось загрузить оборудование",
    ),
  ).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole(
      "button",
      { name: "Повторить" },
    ),
  );

  expect(
    await screen.findByText(
      "У вас пока нет оборудования",
    ),
  ).toBeInTheDocument();
});
