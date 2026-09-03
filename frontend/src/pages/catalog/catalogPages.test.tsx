import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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
  useLocation,
} from "react-router-dom";
import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import { ApplicationRoutes } from "../../app/App";
import { TelegramAccessGate } from "../../features/auth/TelegramAccessGate";
import type {
  CatalogItem,
  CatalogItemListEntry,
  CategoryDetail,
  CategorySummary,
} from "../../shared/api/catalog";

const category: CategorySummary = {
  id: "category-sfp",
  key: "sfp",
  display_name: "SFP-модули",
  description: "Оптические и медные трансиверы",
  default_accounting_mode: "SERIAL",
  sort_order: 10,
  is_system: true,
};

const secondCategory: CategorySummary = {
  id: "category-disk",
  key: "disks",
  display_name: "Диски и накопители",
  description: null,
  default_accounting_mode: "SERIAL",
  sort_order: 20,
  is_system: true,
};

const categoryDetail: CategoryDetail = {
  ...category,
  attributes: [
    {
      id: "attribute-speed",
      key: "speed",
      label: "Скорость",
      data_type: "INTEGER",
      unit: "Гбит/с",
      required: true,
      filterable: true,
      searchable: true,
      card_visible: true,
      detail_visible: true,
      table_visible: true,
      excel_visible: true,
      sort_order: 10,
      filter_type: "RANGE",
      allowed_values: null,
      validation_metadata: null,
      is_system: true,
    },
    {
      id: "attribute-hidden",
      key: "hidden",
      label: "Скрытый detail",
      data_type: "TEXT",
      unit: null,
      required: false,
      filterable: false,
      searchable: false,
      card_visible: false,
      detail_visible: false,
      table_visible: false,
      excel_visible: false,
      sort_order: 20,
      filter_type: "NONE",
      allowed_values: null,
      validation_metadata: null,
      is_system: true,
    },
  ],
};

const itemBase: CatalogItem = {
  id: "item-1",
  category: { id: category.id, key: category.key, display_name: category.display_name },
  manufacturer: { id: "manufacturer-1", name: "Mellanox" },
  name: "Трансивер 100G",
  model: "MFM1T02A-LR",
  manufacturer_part_number: "MFM1T02A-LR-PN",
  internal_code: "SFP-001",
  description: "Одномодовый трансивер",
  accounting_mode: "SERIAL",
  status: "ACTIVE",
  comment: "Проверять совместимость прошивки",
  datasheet_url: "https://example.com/datasheet.pdf",
  technical_data_source: "Спецификация производителя",
  archived_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  attributes: { speed: 100, hidden: "не показывать" },
};

const listItem: CatalogItemListEntry = {
  ...itemBase,
  inventory: { available_count: 2, custody_count: 1, total_count: 3 },
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function createClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Number.POSITIVE_INFINITY,
        refetchOnWindowFocus: false,
      },
    },
  });
}

function renderRoutes(initialEntry: string, children = <ApplicationRoutes />) {
  const client = createClient();
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        {children}
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...result, client };
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location-search">{location.search}</output>;
}

function routesWithLocationProbe() {
  return (
    <>
      <ApplicationRoutes />
      <LocationProbe />
    </>
  );
}

function currentSearchParams(): URLSearchParams {
  return new URLSearchParams(
    screen.getByTestId("location-search").textContent ?? "",
  );
}

function catalogFetch(input: RequestInfo | URL): Promise<Response> {
  const url = String(input);
  if (url === "/api/catalog/categories/sfp") {
    return Promise.resolve(jsonResponse(categoryDetail));
  }
  if (url === "/api/catalog/items/item-1") {
    return Promise.resolve(jsonResponse(itemBase));
  }
  if (url.startsWith("/api/catalog/items/facets?")) {
    return Promise.resolve(jsonResponse({
      facets: [
        {
          key: "availability",
          label: "Наличие",
          data_type: "ENUM",
          unit: null,
          filter_type: "EXACT",
          values: [
            { value: "IN_STOCK", count: 1, label: "В наличии", code: null, name: null },
          ],
          min: null,
          max: null,
        },
        {
          key: "speed",
          label: "Скорость",
          data_type: "INTEGER",
          unit: "Гбит/с",
          filter_type: "RANGE",
          values: [],
          min: 10,
          max: 100,
        },
      ],
    }));
  }
  if (url.startsWith("/api/catalog/items?")) {
    return Promise.resolve(jsonResponse({
      items: [listItem],
      total: 1,
      limit: 20,
      offset: 0,
    }));
  }
  if (url === "/api/catalog/categories") {
    return Promise.resolve(jsonResponse([category, secondCategory]));
  }
  return Promise.reject(new Error(`unexpected fetch: ${url}`));
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  delete window.Telegram;
});

it("после approved access gate показывает рабочий shell и категории API", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/auth/me") {
      return jsonResponse({
        user: {
          id: "user-1",
          telegram_user_id: 1001,
          username: "approved",
          first_name: "Approved",
          last_name: null,
          role: "USER",
          access_status: "APPROVED",
        },
        support: { username: "support", url: "https://t.me/support" },
      });
    }
    return catalogFetch(input);
  });
  vi.stubGlobal("fetch", fetchMock);

  renderRoutes(
    "/catalog",
    <TelegramAccessGate><ApplicationRoutes /></TelegramAccessGate>,
  );

  expect(await screen.findByRole("heading", { name: "Найти оборудование" })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Спикател" })).toHaveAttribute(
    "src",
    "/brand/spikatel-logo-white.svg",
  );
  expect(await screen.findByRole("link", { name: /SFP-модули/ })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Диски и накопители/ })).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "Основная навигация" })).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /Каталог/ }).length).toBeGreaterThan(0);
});

it("показывает отдельное пустое состояние без категорий", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => jsonResponse([])));
  renderRoutes("/catalog");

  expect(await screen.findByText("Категорий пока нет")).toBeInTheDocument();
});

it("показывает ошибку категорий и повторяет запрос", async () => {
  let calls = 0;
  vi.stubGlobal("fetch", vi.fn(async () => {
    calls += 1;
    return calls === 1
      ? jsonResponse({ detail: "failed" }, 500)
      : jsonResponse([category]);
  }));
  renderRoutes("/catalog");

  expect(await screen.findByText("Не удалось загрузить категории")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
  expect(await screen.findByRole("link", { name: /SFP-модули/ })).toBeInTheDocument();
  expect(calls).toBe(2);
});

it("category request содержит key, а смена сортировки меняет query", async () => {
  const fetchMock = vi.fn(catalogFetch);
  vi.stubGlobal("fetch", fetchMock);
  renderRoutes("/catalog/sfp");

  expect(await screen.findByRole("heading", { name: "MFM1T02A-LR" })).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([input]) => {
    const url = String(input);
    return url.startsWith("/api/catalog/items?") && new URL(url, "https://app.test").searchParams.get("category") === "sfp";
  })).toBe(true);

  fireEvent.click(screen.getByRole("button", { name: /По названию/ }));
  fireEvent.click(screen.getByRole("button", { name: /Сначала доступные/ }));

  await waitFor(() => {
    expect(fetchMock.mock.calls.some(([input]) => {
      const params = new URL(String(input), "https://app.test").searchParams;
      return params.get("category") === "sfp"
        && params.get("sort") === "available"
        && params.get("order") === "desc";
    })).toBe(true);
  });
});

it("не дублирует inline back, когда навигацию назад предоставляет Telegram", async () => {
  const backButton = {
    show: vi.fn(),
    hide: vi.fn(),
    onClick: vi.fn(),
    offClick: vi.fn(),
  };

  window.Telegram = {
    WebApp: {
      initData: "signed",
      ready: vi.fn(),
      expand: vi.fn(),
      BackButton: backButton,
    },
  };

  vi.stubGlobal("fetch", vi.fn(catalogFetch));
  renderRoutes("/catalog/sfp");

  expect(await screen.findByRole("heading", { name: "MFM1T02A-LR" })).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Назад в каталог" }),
  ).not.toBeInTheDocument();
  expect(backButton.show).toHaveBeenCalled();
});

it("pending debounce не откатывает более новую сортировку", async () => {
  vi.stubGlobal("fetch", vi.fn(catalogFetch));
  renderRoutes("/catalog/sfp", routesWithLocationProbe());
  await screen.findByRole("heading", { name: "MFM1T02A-LR" });
  vi.useFakeTimers();

  fireEvent.change(
    screen.getByRole("searchbox", { name: "Поиск внутри категории" }),
    { target: { value: "needle" } },
  );
  fireEvent.click(screen.getByRole("button", { name: /По названию/ }));
  fireEvent.click(screen.getByRole("button", { name: /Сначала доступные/ }));
  act(() => vi.advanceTimersByTime(320));

  const params = currentSearchParams();
  expect(params.get("q")).toBe("needle");
  expect(params.get("sort")).toBe("available");
  expect(params.get("order")).toBe("desc");
});

it("pending debounce не откатывает более новый filter state", async () => {
  vi.stubGlobal("fetch", vi.fn(catalogFetch));
  renderRoutes("/catalog/sfp", routesWithLocationProbe());
  await screen.findByRole("heading", { name: "MFM1T02A-LR" });

  fireEvent.click(screen.getByRole("button", { name: "Фильтры" }));
  await screen.findByLabelText("В наличии");
  fireEvent.click(screen.getByRole("button", { name: "Закрыть фильтры" }));
  vi.useFakeTimers();

  fireEvent.change(
    screen.getByRole("searchbox", { name: "Поиск внутри категории" }),
    { target: { value: "needle" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Фильтры" }));
  fireEvent.click(screen.getByLabelText("В наличии"));
  fireEvent.click(screen.getByRole("button", { name: "Применить" }));
  act(() => vi.advanceTimersByTime(320));

  const params = currentSearchParams();
  expect(params.get("q")).toBe("needle");
  expect(params.get("availability")).toBe("IN_STOCK");
});

it("facets загружаются только при открытии фильтров и pageable facet дозагружается", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url.startsWith("/api/catalog/items/facets?")) {
      const params = new URL(url, "https://app.test").searchParams;

      if (params.get("facet") === "manufacturer") {
        expect(params.get("facet_limit")).toBe("50");
        expect(params.get("facet_offset")).toBe("1");

        return jsonResponse({
          facets: [
            {
              key: "manufacturer",
              label: "Производитель",
              data_type: "TEXT",
              unit: null,
              filter_type: "EXACT",
              values_has_more: false,
              values: [
                {
                  value: "manufacturer-page-2",
                  count: 2,
                  label: "NVIDIA page 2",
                  code: null,
                  name: null,
                },
              ],
              min: null,
              max: null,
            },
          ],
        });
      }

      return jsonResponse({
        facets: [
          {
            key: "manufacturer",
            label: "Производитель",
            data_type: "TEXT",
            unit: null,
            filter_type: "EXACT",
            values_has_more: true,
            values: [
              {
                value: "manufacturer-page-1",
                count: 3,
                label: "Mellanox page 1",
                code: null,
                name: null,
              },
            ],
            min: null,
            max: null,
          },
        ],
      });
    }

    return catalogFetch(input);
  });

  vi.stubGlobal("fetch", fetchMock);

  renderRoutes("/catalog/sfp");

  expect(
    await screen.findByRole("heading", { name: "MFM1T02A-LR" }),
  ).toBeInTheDocument();

  const facetCallsBeforeOpen = fetchMock.mock.calls.filter(
    ([input]) =>
      String(input).startsWith("/api/catalog/items/facets?"),
  );

  expect(facetCallsBeforeOpen).toHaveLength(0);

  fireEvent.click(
    screen.getByRole("button", { name: "Фильтры" }),
  );

  expect(
    await screen.findByLabelText("Mellanox page 1"),
  ).toBeInTheDocument();

  const initialFacetCalls = fetchMock.mock.calls.filter(
    ([input]) =>
      String(input).startsWith("/api/catalog/items/facets?"),
  );

  expect(initialFacetCalls).toHaveLength(1);

  fireEvent.click(
    screen.getByRole("button", {
      name: "Показать ещё: Производитель",
    }),
  );

  expect(
    await screen.findByLabelText("NVIDIA page 2"),
  ).toBeInTheDocument();

  const allFacetCalls = fetchMock.mock.calls.filter(
    ([input]) =>
      String(input).startsWith("/api/catalog/items/facets?"),
  );

  expect(allFacetCalls).toHaveLength(2);
});

it("FilterSheet Apply сохраняет текущие q и sort/order", async () => {
  vi.stubGlobal("fetch", vi.fn(catalogFetch));
  renderRoutes(
    "/catalog/sfp?q=existing&sort=total&order=desc",
    routesWithLocationProbe(),
  );
  await screen.findByRole("heading", { name: "MFM1T02A-LR" });

  fireEvent.click(screen.getByRole("button", { name: "Фильтры" }));
  fireEvent.click(await screen.findByLabelText("В наличии"));
  fireEvent.click(screen.getByRole("button", { name: "Применить" }));

  const params = currentSearchParams();
  expect(params.get("q")).toBe("existing");
  expect(params.get("sort")).toBe("total");
  expect(params.get("order")).toBe("desc");
  expect(params.get("availability")).toBe("IN_STOCK");
});

it("facet sheet не показывает previous-query counts как текущие", async () => {
  let resolveNextFacets: ((response: Response) => void) | undefined;
  const nextFacets = new Promise<Response>((resolve) => {
    resolveNextFacets = resolve;
  });
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith("/api/catalog/items/facets?")) {
      const params = new URL(url, "https://app.test").searchParams;
      if (params.get("q") === "needle") {
        return nextFacets;
      }
      return Promise.resolve(jsonResponse({
        facets: [{
          key: "availability",
          label: "Наличие",
          data_type: "ENUM",
          unit: null,
          filter_type: "EXACT",
          values: [{
            value: "IN_STOCK",
            count: 99,
            label: "Старое значение",
            code: null,
            name: null,
          }],
          min: null,
          max: null,
        }],
      }));
    }
    return catalogFetch(input);
  }));
  renderRoutes("/catalog/sfp", routesWithLocationProbe());
  await screen.findByRole("heading", { name: "MFM1T02A-LR" });

  fireEvent.click(screen.getByRole("button", { name: "Фильтры" }));
  expect(await screen.findByLabelText("Старое значение")).toBeInTheDocument();
  expect(screen.getByText("99")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Закрыть фильтры" }));
  vi.useFakeTimers();

  fireEvent.change(
    screen.getByRole("searchbox", { name: "Поиск внутри категории" }),
    { target: { value: "needle" } },
  );
  await act(async () => {
    vi.advanceTimersByTime(320);
    await Promise.resolve();
  });
  fireEvent.click(screen.getByRole("button", { name: "Фильтры" }));

  expect(screen.getByLabelText("Загрузка фильтров")).toBeInTheDocument();
  expect(screen.queryByLabelText("Старое значение")).not.toBeInTheDocument();
  expect(screen.queryByText("99")).not.toBeInTheDocument();

  resolveNextFacets?.(jsonResponse({ facets: [] }));
});

it("detail показывает только detail_visible атрибуты и безопасный datasheet", async () => {
  vi.stubGlobal("fetch", vi.fn(catalogFetch));
  renderRoutes("/catalog/items/item-1");

  expect(await screen.findByRole("heading", { name: "MFM1T02A-LR" })).toBeInTheDocument();
  expect(await screen.findByText("100 Гбит/с")).toBeInTheDocument();
  expect(screen.queryByText("не показывать")).not.toBeInTheDocument();
  expect(screen.getByText("Проверять совместимость прошивки")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Открыть datasheet/ })).toHaveAttribute(
    "href",
    "https://example.com/datasheet.pdf",
  );
});

it("возврат из detail восстанавливает search и filter URL категории", async () => {
  vi.stubGlobal("fetch", vi.fn(catalogFetch));
  renderRoutes("/catalog/sfp?q=needle&filter=speed%3Agte%3A25");

  fireEvent.click(await screen.findByRole("heading", { name: "MFM1T02A-LR" }));
  expect(await screen.findByText("Карточка оборудования")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Назад" }));

  expect(await screen.findByRole("searchbox", { name: "Поиск внутри категории" })).toHaveValue("needle");
  expect(screen.getByRole("button", { name: /Фильтры/ })).toHaveTextContent("1");
});
