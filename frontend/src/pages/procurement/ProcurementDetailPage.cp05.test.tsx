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

import { ProcurementDetailPage } from "./ProcurementDetailPage";

vi.mock(
  "../../features/auth/useAuthState",
  () => ({
    useAuthState: () => ({
      isPending: false,
      data: {
        user: {
          id: "cp05-senior",
          telegram_user_id: 50002,
          username: "senior",
          first_name: "Senior",
          last_name: null,
          role:
            "SENIOR_ENGINEER",
          access_status:
            "APPROVED",
          capabilities: [
            "procurement.read",
            "procurement.accept",
            "catalog.read",
          ],
        },
        support: {
          username: "support",
          url: "https://t.me/support",
        },
      },
    }),
  }),
);

const itemRequests: string[] = [];

const line = {
  id: "line-1",
  line_no: 1,
  line_type: "PROPOSED_ITEM",
  catalog_item_id: null,
  bound_item_id: null,
  expected_identity_signature:
    "0".repeat(64),
  display_snapshot: {
    category_key:
      "transceiver_ethernet",
    manufacturer_name:
      "Generic",
    name:
      "Requested transceiver",
    model:
      "REQ-1",
    attributes: {},
  },
  quantity: 1,
};

const revision = {
  id: "revision-1",
  revision_number: 1,
  submitted_by: {
    id: "cp05-admin",
    display_name:
      "CP05 Admin",
  },
  general_comment: null,
  created_at:
    "2026-09-16T00:00:00Z",
  lines: [line],
};

const request = {
  id: "request-1",
  request_number:
    "PR-2026-0501",
  status: "PURCHASING",
  status_label:
    "В закупке",
  initiator: {
    id: "cp05-admin",
    display_name:
      "CP05 Admin",
  },
  assigned_manager: {
    id: "manager-1",
    display_name:
      "Manager",
  },
  current_revision_id:
    revision.id,
  revision_number: 1,
  line_count: 1,
  state_version: 4,
  created_at:
    "2026-09-16T00:00:00Z",
  updated_at:
    "2026-09-16T00:00:00Z",
  completed_at: null,
  current_revision: revision,
  revisions: [revision],
  events: [],
  final_movement_id: null,
  available_actions: [
    "bind_lines",
  ],
};

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

function catalogItem(
  position: number,
) {
  return {
    id: `bind-item-${position}`,
    category: {
      id: "category-1",
      key:
        "transceiver_ethernet",
      display_name:
        "Ethernet transceivers",
    },
    manufacturer: {
      id: "manufacturer-1",
      name: "Vendor",
    },
    name:
      `Bind ${String(
        position,
      ).padStart(3, "0")}`,
    model:
      `B${String(
        position,
      ).padStart(3, "0")}`,
    status: "ACTIVE",
    archived_at: null,
    created_at:
      "2026-09-16T00:00:00Z",
    updated_at:
      "2026-09-16T00:00:00Z",
    attributes: {},
    inventory: {
      available_count: 0,
      total_count: 0,
    },
  };
}

function renderPage() {
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

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[
          "/procurement/request-1",
        ]}
      >
        <Routes>
          <Route
            path="/procurement/:requestId"
            element={
              <ProcurementDetailPage />
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
  vi.clearAllMocks();
  itemRequests.length = 0;
});

it(
  "binding picker can load catalog matches beyond the first page",
  async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async (
          input: RequestInfo | URL,
        ) => {
          const url = String(input);

          if (
            url
            === "/api/procurement/requests/request-1"
          ) {
            return jsonResponse(
              request,
            );
          }

          if (
            url.startsWith(
              "/api/catalog/items?",
            )
          ) {
            itemRequests.push(url);

            const params =
              new URL(
                url,
                "http://test",
              ).searchParams;

            const limit = Number(
              params.get("limit")
              ?? "20",
            );
            const offset = Number(
              params.get("offset")
              ?? "0",
            );

            const total = 205;
            const count =
              Math.max(
                0,
                Math.min(
                  limit,
                  total - offset,
                ),
              );

            return jsonResponse({
              items: Array.from(
                {
                  length: count,
                },
                (_, row) =>
                  catalogItem(
                    offset + row,
                  ),
              ),
              total,
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

    renderPage();

    fireEvent.click(
      await screen.findByRole(
        "button",
        {
          name: "Связать",
        },
      ),
    );

    fireEvent.change(
      screen.getByLabelText(
        "Поиск",
      ),
      {
        target: {
          value: "bind",
        },
      },
    );

    await screen.findByRole(
      "button",
      {
        name:
          "Vendor · Bind 000 · B000",
      },
    );

    const initialResultCount =
      screen.getAllByRole(
        "button",
        {
          name:
            /Vendor · Bind/,
        },
      ).length;

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
          (requestUrl) =>
            Number(
              new URL(
                requestUrl,
                "http://test",
              ).searchParams.get(
                "offset",
              ) ?? "0",
            ) > 0,
        ),
      ).toBe(true);
    });

    await waitFor(() => {
      expect(
        screen.getAllByRole(
          "button",
          {
            name:
              /Vendor · Bind/,
          },
        ).length,
      ).toBeGreaterThan(
        initialResultCount,
      );
    });
  },
);
