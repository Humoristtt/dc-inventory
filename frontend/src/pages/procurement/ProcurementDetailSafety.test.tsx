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
  type Capability,
  type UserRole,
} from "../../shared/api/auth";
import type {
  ProcurementLine,
  ProcurementRequest,
} from "../../shared/api/procurement";
import { ProcurementDetailPage } from "./ProcurementDetailPage";

function capabilities(role: UserRole): Capability[] {
  if (role === "MANAGER") {
    return [
      "catalog.read",
      "inventory.read",
      "procurement.read",
      "procurement.manage",
    ];
  }

  return [
    "catalog.read",
    "catalog.manage",
    "inventory.read",
    "inventory.operate",
    "movement.read_own",
    "movement.read_all",
    "procurement.read",
    "procurement.accept",
  ];
}

function authState(role: "MANAGER" | "SENIOR_ENGINEER"): AuthState {
  return {
    user: {
      id: `user-${role.toLowerCase()}`,
      telegram_user_id: 2001,
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

const existingLine: ProcurementLine = {
  id: "line-1",
  line_no: 1,
  line_type: "EXISTING_ITEM",
  catalog_item_id: "item-1",
  bound_item_id: "item-1",
  display_snapshot: {
    manufacturer_name: "Vendor",
    name: "Existing item",
    model: "EX-1",
  },
  quantity: 1,
};

const proposedLine: ProcurementLine = {
  id: "line-2",
  line_no: 1,
  line_type: "PROPOSED_ITEM",
  catalog_item_id: null,
  bound_item_id: null,
  display_snapshot: {
    category_key: "transceiver_ethernet",
    manufacturer_name: "Vendor",
    name: "Proposed item",
    model: "PR-1",
    attributes: {},
  },
  quantity: 1,
};

function procurementRequest(
  availableActions: string[],
  line: ProcurementLine = existingLine,
): ProcurementRequest {
  const revision = {
    id: "revision-1",
    revision_number: 1,
    submitted_by: {
      id: "user-admin",
      display_name: "Admin",
    },
    general_comment: null,
    created_at: "2026-09-30T00:00:00Z",
    lines: [line],
  };

  return {
    id: "request-1",
    request_number: "PR-2026-0701",
    status: "AWAITING_ACCEPTANCE",
    status_label: "Ожидает приёмки",
    initiator: {
      id: "user-admin",
      display_name: "Admin",
    },
    assigned_manager: {
      id: "user-manager",
      display_name: "Manager",
    },
    current_revision_id: revision.id,
    revision_number: 1,
    line_count: 1,
    state_version: 7,
    created_at: "2026-09-30T00:00:00Z",
    updated_at: "2026-09-30T00:00:00Z",
    completed_at: null,
    current_revision: revision,
    revisions: [revision],
    events: [],
    final_movement_id: null,
    available_actions: availableActions,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
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

function renderDetail(
  role: "MANAGER" | "SENIOR_ENGINEER",
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
    authState(role),
  );

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
            element={<ProcurementDetailPage />}
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
});

it(
  "submits at most one immediate action while the first request is pending",
  async () => {
    const request = procurementRequest([
      "manager_accept",
    ]);
    let resolveMutation:
      | ((response: Response) => void)
      | undefined;
    const pending = new Promise<Response>(
      (resolve) => {
        resolveMutation = resolve;
      },
    );
    const bodies: Record<string, unknown>[] = [];

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
            === "/api/procurement/requests/request-1"
          ) {
            return jsonResponse(request);
          }

          if (
            url
            === "/api/procurement/requests/request-1/manager-accept"
          ) {
            bodies.push(
              JSON.parse(
                String(init?.body),
              ) as Record<string, unknown>,
            );
            return pending;
          }

          throw new Error(
            `unexpected fetch ${url}`,
          );
        },
      ),
    );

    renderDetail("MANAGER");

    const action =
      await screen.findByRole(
        "button",
        {
          name: "Принять в работу",
        },
      );

    fireEvent.click(action);
    fireEvent.click(action);

    await waitFor(() => {
      expect(bodies).toHaveLength(1);
    });

    expect(
      (action as HTMLButtonElement).disabled,
    ).toBe(true);

    resolveMutation?.(
      jsonResponse(
        procurementRequest([]),
      ),
    );

    await waitFor(() => {
      expect(
        screen.queryByText("Сохраняем…"),
      ).toBeNull();
    });
  },
);

it(
  "reuses the action key after a lost response and rotates it when the payload changes",
  async () => {
    const request = procurementRequest([
      "report_discrepancy",
    ]);
    const bodies: Record<string, unknown>[] = [];
    let postCount = 0;

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
            === "/api/procurement/requests/request-1"
          ) {
            return jsonResponse(request);
          }

          if (
            url
            === "/api/procurement/requests/request-1/discrepancies"
          ) {
            bodies.push(
              JSON.parse(
                String(init?.body),
              ) as Record<string, unknown>,
            );
            postCount += 1;

            if (postCount < 3) {
              throw new TypeError(
                "lost response after commit",
              );
            }

            return jsonResponse(request);
          }

          throw new Error(
            `unexpected fetch ${url}`,
          );
        },
      ),
    );

    renderDetail("SENIOR_ENGINEER");

    fireEvent.click(
      await screen.findByRole(
        "button",
        {
          name: "Есть расхождения",
        },
      ),
    );

    const comment =
      screen.getByLabelText(
        "Что отличается",
      );
    fireEvent.change(
      comment,
      {
        target: {
          value: "Первое описание",
        },
      },
    );

    const submit =
      screen.getByRole(
        "button",
        {
          name: "Зафиксировать",
        },
      );

    for (const count of [1, 2]) {
      fireEvent.click(submit);
      await waitFor(() => {
        expect(bodies).toHaveLength(count);
      });
      await screen.findByRole("alert");
      await waitFor(() => {
        expect(
          (submit as HTMLButtonElement).disabled,
        ).toBe(false);
      });
    }

    expect(
      bodies[1].client_request_id,
    ).toBe(
      bodies[0].client_request_id,
    );

    fireEvent.change(
      comment,
      {
        target: {
          value: "Изменённое описание",
        },
      },
    );
    fireEvent.click(submit);

    await waitFor(() => {
      expect(bodies).toHaveLength(3);
    });

    expect(
      bodies[2].client_request_id,
    ).not.toBe(
      bodies[0].client_request_id,
    );
  },
);

it(
  "shows manager lookup failure separately from an empty result and can retry",
  async () => {
    const request = procurementRequest([
      "transfer_manager",
    ]);
    let managerCalls = 0;

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
            return jsonResponse(request);
          }

          if (
            url.startsWith(
              "/api/procurement/managers?",
            )
          ) {
            managerCalls += 1;
            if (managerCalls === 1) {
              return jsonResponse(
                { detail: "failed" },
                500,
              );
            }
            return jsonResponse({
              items: [
                {
                  id: "manager-2",
                  display_name: "Manager Two",
                },
              ],
              total: 1,
              limit: 50,
              offset: 0,
            });
          }

          throw new Error(
            `unexpected fetch ${url}`,
          );
        },
      ),
    );

    renderDetail("MANAGER");

    fireEvent.click(
      await screen.findByRole(
        "button",
        {
          name: "Передать менеджеру",
        },
      ),
    );

    expect(
      await screen.findByText(
        /Не удалось загрузить менеджеров/,
      ),
    ).toBeTruthy();

    fireEvent.click(
      screen.getByRole(
        "button",
        {
          name: "Повторить",
        },
      ),
    );

    expect(
      await screen.findByRole(
        "option",
        {
          name: "Manager Two",
        },
      ),
    ).toBeTruthy();
  },
);

it(
  "shows location lookup failure separately from no active locations and can retry",
  async () => {
    const request = procurementRequest([
      "complete_acceptance",
    ]);
    let locationCalls = 0;

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
            return jsonResponse(request);
          }

          if (
            url
            === "/api/inventory/locations?limit=200&offset=0"
          ) {
            locationCalls += 1;
            if (locationCalls === 1) {
              return jsonResponse(
                { detail: "failed" },
                500,
              );
            }
            return jsonResponse({
              items: [
                {
                  id: "location-1",
                  code: "WH-01",
                  name: "Warehouse",
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

          throw new Error(
            `unexpected fetch ${url}`,
          );
        },
      ),
    );

    renderDetail("SENIOR_ENGINEER");

    fireEvent.click(
      await screen.findByRole(
        "button",
        {
          name: "Подтвердить приёмку",
        },
      ),
    );

    expect(
      await screen.findByText(
        /Не удалось загрузить места приёмки/,
      ),
    ).toBeTruthy();

    fireEvent.click(
      screen.getByRole(
        "button",
        {
          name: "Повторить",
        },
      ),
    );

    expect(
      await screen.findByRole(
        "option",
        {
          name: "Warehouse · WH-01",
        },
      ),
    ).toBeTruthy();
  },
);

it(
  "shows binding lookup failure separately from an empty search and can retry",
  async () => {
    const request = procurementRequest(
      ["bind_lines"],
      proposedLine,
    );
    let catalogCalls = 0;

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
            return jsonResponse(request);
          }

          if (
            url.startsWith(
              "/api/catalog/items?",
            )
          ) {
            catalogCalls += 1;
            if (catalogCalls === 1) {
              return jsonResponse(
                { detail: "failed" },
                500,
              );
            }

            return jsonResponse({
              items: [
                {
                  id: "item-match",
                  category: {
                    id: "category-1",
                    key: "transceiver_ethernet",
                    display_name: "Transceivers",
                  },
                  manufacturer: {
                    id: "manufacturer-1",
                    name: "Vendor",
                  },
                  name: "Match",
                  model: "M1",
                  status: "ACTIVE",
                  archived_at: null,
                  created_at: "2026-09-30T00:00:00Z",
                  updated_at: "2026-09-30T00:00:00Z",
                  attributes: {},
                  inventory: {
                    available_count: 0,
                    total_count: 0,
                  },
                },
              ],
              total: 1,
              limit: 20,
              offset: 0,
            });
          }

          throw new Error(
            `unexpected fetch ${url}`,
          );
        },
      ),
    );

    renderDetail("SENIOR_ENGINEER");

    fireEvent.click(
      await screen.findByRole(
        "button",
        {
          name: "Связать",
        },
      ),
    );

    fireEvent.change(
      screen.getByLabelText("Поиск"),
      {
        target: {
          value: "match",
        },
      },
    );

    expect(
      await screen.findByText(
        /Не удалось загрузить оборудование/,
      ),
    ).toBeTruthy();

    fireEvent.click(
      screen.getByRole(
        "button",
        {
          name: "Повторить",
        },
      ),
    );

    expect(
      await screen.findByRole(
        "button",
        {
          name: "Vendor · Match · M1",
        },
      ),
    ).toBeTruthy();
  },
);
