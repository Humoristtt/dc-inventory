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
} from "@testing-library/react";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import type { CatalogItem } from "../../shared/api/catalog";
import {
  AUTH_QUERY_KEY,
  type AuthState,
  type Capability,
} from "../../shared/api/auth";
import { AdminItemActions } from "./AdminItemActions";

const item: CatalogItem = {
  id: "item-1",
  category: {
    id: "category-1",
    key: "sfp",
    display_name: "SFP",
  },
  manufacturer: null,
  name: "Synthetic SFP",
  model: "TEST-1",
  status: "ACTIVE",
  archived_at: null,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  attributes: {},
};

function jsonResponse(
  body: unknown,
  status = 200,
): Response {
  return new Response(
    JSON.stringify(body),
    {
      status,
      headers: {
        "Content-Type": "application/json",
      },
    },
  );
}

function authState(
  capabilities: Capability[],
): AuthState {
  return {
    user: {
      id: "user-1",
      telegram_user_id: 1001,
      username: "tester",
      first_name: "Test",
      last_name: null,
      role: "SENIOR_ENGINEER",
      capabilities,
      access_status: "APPROVED",
    },
    support: {
      username: "support",
      url: "https://t.me/support",
    },
  };
}

function LocationProbe() {
  const location = useLocation();

  return (
    <output data-testid="location">
      {location.pathname}
    </output>
  );
}

function renderActions(
  capabilities: Capability[],
) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
      mutations: {
        retry: false,
      },
    },
  });

  client.setQueryData(
    AUTH_QUERY_KEY,
    authState(capabilities),
  );

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[
          "/catalog/items/item-1",
        ]}
      >
        <Routes>
          <Route
            path="*"
            element={
              <>
                <AdminItemActions item={item} />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it(
  "delete_unused удаляет никогда не использованную позицию и возвращает в категорию",
  async () => {
    const fetchMock = vi.fn(
      async (
        input: RequestInfo | URL,
        init?: RequestInit,
      ) => {
        const url = String(input);

        if (
          url
            === "/api/admin/catalog/items/item-1"
          && init?.method === "DELETE"
        ) {
          return new Response(null, {
            status: 204,
          });
        }

        throw new Error(
          `unexpected fetch: ${url}`,
        );
      },
    );

    vi.stubGlobal("fetch", fetchMock);

    renderActions([
      "catalog.read",
      "catalog.manage",
      "catalog.archive",
      "catalog.delete_unused",
    ]);

    fireEvent.click(
      screen.getByRole(
        "button",
        { name: "Удалить позицию" },
      ),
    );

    expect(
      screen.getByRole(
        "dialog",
        {
          name:
            "Удалить позицию безвозвратно?",
        },
      ),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole(
        "button",
        { name: "Удалить безвозвратно" },
      ),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/catalog/items/item-1",
        expect.objectContaining({
          method: "DELETE",
          credentials: "same-origin",
        }),
      );
    });

    await waitFor(() => {
      expect(
        screen.getByTestId("location"),
      ).toHaveTextContent("/catalog/sfp");
    });
  },
);

it(
  "не показывает hard delete без catalog.delete_unused",
  () => {
    renderActions([
      "catalog.read",
      "catalog.manage",
      "catalog.archive",
    ]);

    expect(
      screen.getByRole(
        "link",
        { name: "Редактировать" },
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByRole(
        "button",
        { name: "В архив" },
      ),
    ).toBeInTheDocument();

    expect(
      screen.queryByRole(
        "button",
        { name: "Удалить позицию" },
      ),
    ).not.toBeInTheDocument();
  },
);

it(
  "показывает понятную ошибку если позиция уже использовалась",
  async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async (
          input: RequestInfo | URL,
          init?: RequestInit,
        ) => {
          const url = String(input);

          if (
            url
              === "/api/admin/catalog/items/item-1"
            && init?.method === "DELETE"
          ) {
            return jsonResponse(
              {
                detail: {
                  code: "catalog_item_in_use",
                  message:
                    "item has warehouse history and cannot be deleted",
                },
              },
              409,
            );
          }

          throw new Error(
            `unexpected fetch: ${url}`,
          );
        },
      ),
    );

    renderActions([
      "catalog.read",
      "catalog.manage",
      "catalog.archive",
      "catalog.delete_unused",
    ]);

    fireEvent.click(
      screen.getByRole(
        "button",
        { name: "Удалить позицию" },
      ),
    );

    fireEvent.click(
      screen.getByRole(
        "button",
        { name: "Удалить безвозвратно" },
      ),
    );

    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent(
      "Удалить нельзя: позиция уже использовалась в складском учёте.",
    );

    expect(
      screen.getByTestId("location"),
    ).toHaveTextContent(
      "/catalog/items/item-1",
    );
  },
);
