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
import {
  afterEach,
  beforeEach,
  expect,
  it,
  vi,
} from "vitest";

import { LineComposer } from "./LineComposer";

const category = {
  id: "category-transceiver",
  key: "transceiver_ethernet",
  display_name: "Ethernet transceivers",
  description: null,
  sort_order: 10,
  is_system: true,
  parent_id: null,
};

const manufacturerRequests: string[] = [];
const itemRequests: string[] = [];

function jsonResponse(body: unknown): Response {
  return new Response(
    JSON.stringify(body),
    {
      status: 200,
      headers: {
        "Content-Type": "application/json",
      },
    },
  );
}

function numberParam(
  params: URLSearchParams,
  name: string,
  fallback: number,
): number {
  const value = Number(params.get(name) ?? fallback);
  return Number.isFinite(value) ? value : fallback;
}

function manufacturer(
  index: number,
) {
  return {
    id: `manufacturer-${index}`,
    name: `Vendor ${String(index).padStart(3, "0")}`,
    created_at: "2026-09-16T00:00:00Z",
    updated_at: "2026-09-16T00:00:00Z",
  };
}

function item(
  id: string,
  name: string,
  model: string,
) {
  return {
    id,
    category: {
      id: category.id,
      key: category.key,
      display_name: category.display_name,
    },
    manufacturer: {
      id: "manufacturer-main",
      name: "Vendor",
    },
    name,
    model,
    status: "ACTIVE",
    archived_at: null,
    created_at: "2026-09-16T00:00:00Z",
    updated_at: "2026-09-16T00:00:00Z",
    attributes: {},
    inventory: {
      available_count: 0,
      total_count: 0,
    },
  };
}

function renderComposer(
  onChange = vi.fn(),
) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  const view = render(
    <QueryClientProvider client={client}>
      <LineComposer
        lines={[]}
        onChange={onChange}
      />
    </QueryClientProvider>,
  );

  return {
    ...view,
    client,
    onChange,
  };
}

beforeEach(() => {
  manufacturerRequests.length = 0;
  itemRequests.length = 0;

  vi.stubGlobal(
    "fetch",
    vi.fn(
      async (
        input: RequestInfo | URL,
      ) => {
        const url = String(input);

        if (url === "/api/catalog/categories") {
          return jsonResponse([category]);
        }

        if (
          url
          === "/api/catalog/categories/transceiver_ethernet"
        ) {
          return jsonResponse({
            ...category,
            attributes: [],
          });
        }

        if (
          url.startsWith(
            "/api/catalog/manufacturers?",
          )
        ) {
          manufacturerRequests.push(url);

          const params = new URL(
            url,
            "http://test",
          ).searchParams;

          const query = params.get("q") ?? "";
          const limit = numberParam(
            params,
            "limit",
            50,
          );
          const offset = numberParam(
            params,
            "offset",
            0,
          );

          if (query === "Tail Vendor") {
            return jsonResponse({
              items: [
                {
                  id: "manufacturer-tail",
                  name: "Tail Vendor",
                  created_at:
                    "2026-09-16T00:00:00Z",
                  updated_at:
                    "2026-09-16T00:00:00Z",
                },
              ],
              total: 1,
              limit,
              offset,
            });
          }

          const total = 205;
          const count = Math.max(
            0,
            Math.min(
              limit,
              total - offset,
            ),
          );

          return jsonResponse({
            items: Array.from(
              { length: count },
              (_, row) =>
                manufacturer(offset + row),
            ),
            total,
            limit,
            offset,
          });
        }

        if (
          url.startsWith(
            "/api/catalog/items?",
          )
        ) {
          itemRequests.push(url);

          const params = new URL(
            url,
            "http://test",
          ).searchParams;

          const query = params.get("q") ?? "";
          const limit = numberParam(
            params,
            "limit",
            20,
          );
          const offset = numberParam(
            params,
            "offset",
            0,
          );

          if (query === "alpha") {
            return jsonResponse({
              items: [
                item(
                  "item-alpha",
                  "Alpha",
                  "A1",
                ),
              ],
              total: 1,
              limit,
              offset,
            });
          }

          if (query === "beta") {
            return jsonResponse({
              items: [
                item(
                  "item-beta",
                  "Beta",
                  "B1",
                ),
              ],
              total: 1,
              limit,
              offset,
            });
          }

          if (query === "needle") {
            const total = 205;
            const count = Math.max(
              0,
              Math.min(
                limit,
                total - offset,
              ),
            );

            return jsonResponse({
              items: Array.from(
                { length: count },
                (_, row) => {
                  const position =
                    offset + row;

                  return item(
                    `item-${position}`,
                    `Needle ${String(
                      position,
                    ).padStart(3, "0")}`,
                    `N${String(
                      position,
                    ).padStart(3, "0")}`,
                  );
                },
              ),
              total,
              limit,
              offset,
            });
          }

          return jsonResponse({
            items: [],
            total: 0,
            limit,
            offset,
          });
        }

        throw new Error(
          `unexpected fetch ${url}`,
        );
      },
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

it(
  "manufacturer lookup searches and paginates instead of loading one fixed block",
  async () => {
    renderComposer();

    fireEvent.click(
      screen.getByRole(
        "button",
        {
          name: "Новая позиция",
        },
      ),
    );

    const categorySelect =
      await screen.findByLabelText(
        "Категория",
      );

    await screen.findByRole(
      "option",
      {
        name:
          "Ethernet transceivers",
      },
    );

    fireEvent.change(
      categorySelect,
      {
        target: {
          value:
            "transceiver_ethernet",
        },
      },
    );

    const search =
      await screen.findByLabelText(
        "Поиск производителя",
      );

    const more =
      await screen.findByRole(
        "button",
        {
          name:
            /Показать ещё.*производ/i,
        },
      );

    fireEvent.click(more);

    await waitFor(() => {
      expect(
        manufacturerRequests.some(
          (requestUrl) => {
            const params =
              new URL(
                requestUrl,
                "http://test",
              ).searchParams;

            return (
              Number(
                params.get(
                  "offset",
                ) ?? "0",
              ) > 0
            );
          },
        ),
      ).toBe(true);
    });

    fireEvent.change(
      search,
      {
        target: {
          value: "Tail Vendor",
        },
      },
    );

    await waitFor(() => {
      expect(
        manufacturerRequests.some(
          (requestUrl) =>
            new URL(
              requestUrl,
              "http://test",
            ).searchParams.get("q")
            === "Tail Vendor",
        ),
      ).toBe(true);
    });

    expect(
      await screen.findByRole(
        "option",
        {
          name: "Tail Vendor",
        },
      ),
    ).toBeTruthy();
  },
);

it(
  "existing catalog picker can load results beyond the initial page",
  async () => {
    renderComposer();

    fireEvent.change(
      screen.getByLabelText(
        "Поиск по каталогу",
      ),
      {
        target: {
          value: "needle",
        },
      },
    );

    const selector =
      await screen.findByLabelText(
        "Позиция",
      );

    await screen.findByRole(
      "option",
      {
        name:
          "Vendor · Needle 000 · N000",
      },
    );

    const initialCount =
      within(selector)
        .getAllByRole("option")
        .length;

    const more =
      await screen.findByRole(
        "button",
        {
          name:
            /Показать ещё/i,
        },
      );

    fireEvent.click(more);

    await waitFor(() => {
      expect(
        itemRequests.some(
          (requestUrl) => {
            const params =
              new URL(
                requestUrl,
                "http://test",
              ).searchParams;

            return (
              params.get("q")
                === "needle"
              && Number(
                params.get(
                  "offset",
                ) ?? "0",
              ) > 0
            );
          },
        ),
      ).toBe(true);
    });

    await waitFor(() => {
      expect(
        within(selector)
          .getAllByRole("option")
          .length,
      ).toBeGreaterThan(
        initialCount,
      );
    });
  },
);

it(
  "changing catalog search invalidates the previously selected item",
  async () => {
    const onChange = vi.fn();

    renderComposer(onChange);

    const search =
      screen.getByLabelText(
        "Поиск по каталогу",
      );

    fireEvent.change(
      search,
      {
        target: {
          value: "alpha",
        },
      },
    );

    const selector =
      await screen.findByLabelText(
        "Позиция",
      );

    await screen.findByRole(
      "option",
      {
        name:
          "Vendor · Alpha · A1",
      },
    );

    fireEvent.change(
      selector,
      {
        target: {
          value: "item-alpha",
        },
      },
    );

    fireEvent.change(
      search,
      {
        target: {
          value: "beta",
        },
      },
    );

    await screen.findByRole(
      "option",
      {
        name:
          "Vendor · Beta · B1",
      },
    );

    fireEvent.click(
      screen.getByRole(
        "button",
        {
          name:
            "Добавить позицию",
        },
      ),
    );

    expect(
      onChange,
    ).not.toHaveBeenCalled();

    expect(
      screen.getByRole("alert")
        .textContent,
    ).toContain(
      "Выберите позицию каталога",
    );
  },
);
