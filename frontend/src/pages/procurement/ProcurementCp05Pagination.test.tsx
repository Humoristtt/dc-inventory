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
} from "../../shared/api/auth";
import {
  getProcurementRequests,
  type ProcurementPage,
  type ProcurementSummary,
} from "../../shared/api/procurement";
import { ProcurementListPage } from "./ProcurementListPage";

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

function seniorEngineerAuth(): AuthState {
  return {
    user: {
      id: "user-senior",
      telegram_user_id: 1001,
      username: "senior",
      first_name: "Senior",
      last_name: null,
      role: "SENIOR_ENGINEER",
      capabilities: [
        "catalog.read",
        "procurement.read",
      ],
      access_status: "APPROVED",
    },
    support: {
      username: "support",
      url: "https://t.me/support",
    },
  };
}

function summary(position: number): ProcurementSummary {
  const number = String(position).padStart(4, "0");

  return {
    id: `request-${position}`,
    request_number: `PR-${number}`,
    status: "AGREEMENT_PENDING_MANAGER",
    status_label: "На согласовании",
    initiator: {
      id: "user-initiator",
      display_name: "Инициатор",
    },
    assigned_manager: {
      id: "user-manager",
      display_name: "Менеджер",
    },
    current_revision_id: `revision-${position}`,
    revision_number: 1,
    line_count: 1,
    state_version: 1,
    created_at: "2026-09-16T00:00:00Z",
    updated_at: "2026-09-16T00:00:00Z",
    completed_at: null,
  };
}

function renderList() {
  const client = makeClient();

  client.setQueryData(
    AUTH_QUERY_KEY,
    seniorEngineerAuth(),
  );

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

  return {
    ...view,
    client,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it(
  "Procurement API requests an explicit page instead of forcing offset zero",
  async () => {
    const fetchMock = vi.fn(
      async () =>
        jsonResponse({
          items: [],
          total: 31,
          limit: 30,
          offset: 30,
        }),
    );

    vi.stubGlobal("fetch", fetchMock);

    const pagedGetProcurementRequests =
      getProcurementRequests as unknown as (
        view: "my" | "active" | "history",
        page: {
          limit: number;
          offset: number;
        },
        signal?: AbortSignal,
      ) => Promise<ProcurementPage>;

    await pagedGetProcurementRequests(
      "active",
      {
        limit: 30,
        offset: 30,
      },
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/procurement/requests?view=active&limit=30&offset=30",
      expect.objectContaining({
        credentials: "same-origin",
      }),
    );
  },
);

it(
  "Procurement queue loads requests beyond the first 30 rows",
  async () => {
    const firstPage = Array.from(
      { length: 30 },
      (_, index) => summary(index + 1),
    );

    const fetchMock = vi.fn(
      async (input: RequestInfo | URL) => {
        const url = String(input);

        if (
          url
          === "/api/procurement/requests?view=active&limit=30&offset=0"
        ) {
          return jsonResponse({
            items: firstPage,
            total: 31,
            limit: 30,
            offset: 0,
          });
        }

        if (
          url
          === "/api/procurement/requests?view=active&limit=30&offset=30"
        ) {
          return jsonResponse({
            items: [summary(31)],
            total: 31,
            limit: 30,
            offset: 30,
          });
        }

        throw new Error(
          `unexpected fetch ${url}`,
        );
      },
    );

    vi.stubGlobal("fetch", fetchMock);

    renderList();

    expect(
      await screen.findByText("PR-0030"),
    ).toBeTruthy();

    expect(
      screen.queryByText("PR-0031"),
    ).toBeNull();

    const loadMore = await screen.findByRole(
      "button",
      {
        name: "Показать ещё",
      },
    );

    fireEvent.click(loadMore);

    expect(
      await screen.findByText("PR-0031"),
    ).toBeTruthy();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/procurement/requests?view=active&limit=30&offset=30",
        expect.anything(),
      );
    });

    expect(
      screen.getAllByRole("link").filter(
        (element) =>
          element.getAttribute("href")
            ?.startsWith("/procurement/request-"),
      ),
    ).toHaveLength(31);
  },
);
