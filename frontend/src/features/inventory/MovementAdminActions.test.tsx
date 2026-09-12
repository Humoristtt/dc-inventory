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
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import {
  AUTH_QUERY_KEY,
  type AuthState,
  type Capability,
} from "../../shared/api/auth";
import type {
  Movement,
} from "../../shared/api/inventory";
import {
  MovementAdminActions,
} from "./MovementAdminActions";

const movement: Movement = {
  id: "movement-1",
  journal_seq: 42,
  occurred_at: "2026-09-12T00:00:00Z",
  actor_user_id: "actor-1",
  custody_user_id: null,
  actor_display_name_snapshot: "Test Admin",
  movement_type: "RECEIPT",
  source_location_id: null,
  destination_location_id: "location-1",
  source_location_name_snapshot: null,
  destination_location_name_snapshot: "Основной склад",
  original_movement_id: null,
  lines: [
    {
      id: "line-1",
      item_id: "item-1",
      item_name_snapshot: "Synthetic item",
      quantity: 5,
    },
  ],
};

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
      role: "ADMIN",
      capabilities,
      access_status: "APPROVED",
    },
    support: {
      username: "support",
      url: "https://t.me/support",
    },
  };
}

function renderActions(
  capabilities: Capability[],
  value: Movement = movement,
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
      <MovementAdminActions
        movement={value}
      />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it(
  "скрывает correction и reversal без inventory.admin",
  () => {
    renderActions([
      "catalog.read",
      "inventory.read",
      "movement.read_all",
    ]);

    expect(
      screen.queryByRole(
        "button",
        { name: "Корректировать остаток" },
      ),
    ).not.toBeInTheDocument();

    expect(
      screen.queryByRole(
        "button",
        { name: "Отменить операцию" },
      ),
    ).not.toBeInTheDocument();
  },
);

it(
  "создаёт CORRECTION относительно исходного movement и его location",
  async () => {
    let submittedBody:
      | Record<string, unknown>
      | undefined;

    const fetchMock = vi.fn(
      async (
        input: RequestInfo | URL,
        init?: RequestInit,
      ) => {
        const url = String(input);

        if (
          url === "/api/inventory/movements"
          && init?.method === "POST"
        ) {
          submittedBody = JSON.parse(
            String(init.body),
          ) as Record<string, unknown>;

          return new Response(
            JSON.stringify({
              ...movement,
              id: "correction-1",
              journal_seq: 43,
              movement_type: "CORRECTION",
              source_location_id: null,
              destination_location_id:
                "location-1",
              original_movement_id:
                "movement-1",
            }),
            {
              status: 201,
              headers: {
                "Content-Type":
                  "application/json",
              },
            },
          );
        }

        throw new Error(
          `unexpected fetch: ${url}`,
        );
      },
    );

    vi.stubGlobal("fetch", fetchMock);

    renderActions([
      "catalog.read",
      "inventory.read",
      "inventory.admin",
      "movement.read_all",
    ]);

    fireEvent.click(
      screen.getByRole(
        "button",
        { name: "Корректировать остаток" },
      ),
    );

    expect(
      screen.getByRole(
        "dialog",
        { name: "Скорректировать остаток" },
      ),
    ).toBeInTheDocument();

    fireEvent.change(
      screen.getByRole("spinbutton", {
        name: /Количество: Synthetic item/,
      }),
      {
        target: {
          value: "2",
        },
      },
    );

    fireEvent.click(
      screen.getByRole(
        "button",
        { name: "Создать корректировку" },
      ),
    );

    await waitFor(() => {
      expect(submittedBody).toBeDefined();
    });

    expect(submittedBody).toMatchObject({
      movement_type: "CORRECTION",
      original_movement_id: "movement-1",
      destination_location_id:
        "location-1",
      lines: [
        {
          item_id: "item-1",
          quantity: 2,
        },
      ],
    });

    expect(
      submittedBody?.source_location_id,
    ).toBeUndefined();

    expect(
      String(
        submittedBody?.client_request_id,
      ),
    ).toMatch(/^correction-/);

    await waitFor(() => {
      expect(
        screen.queryByRole(
          "dialog",
          {
            name:
              "Скорректировать остаток",
          },
        ),
      ).not.toBeInTheDocument();
    });
  },
);

it(
  "создаёт server-side REVERSAL исходной операции",
  async () => {
    let submittedBody:
      | Record<string, unknown>
      | undefined;

    const fetchMock = vi.fn(
      async (
        input: RequestInfo | URL,
        init?: RequestInit,
      ) => {
        const url = String(input);

        if (
          url
            === "/api/admin/inventory/movements/movement-1/reversal"
          && init?.method === "POST"
        ) {
          submittedBody = JSON.parse(
            String(init.body),
          ) as Record<string, unknown>;

          return new Response(
            JSON.stringify({
              ...movement,
              id: "reversal-1",
              journal_seq: 43,
              movement_type: "REVERSAL",
              source_location_id:
                "location-1",
              destination_location_id:
                null,
              original_movement_id:
                "movement-1",
            }),
            {
              status: 201,
              headers: {
                "Content-Type":
                  "application/json",
              },
            },
          );
        }

        throw new Error(
          `unexpected fetch: ${url}`,
        );
      },
    );

    vi.stubGlobal("fetch", fetchMock);

    renderActions([
      "catalog.read",
      "inventory.read",
      "inventory.admin",
      "movement.read_all",
    ]);

    fireEvent.click(
      screen.getByRole(
        "button",
        { name: "Отменить операцию" },
      ),
    );

    expect(
      screen.getByRole(
        "dialog",
        {
          name:
            "Отменить операцию № 42?",
        },
      ),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole(
        "button",
        { name: "Создать отмену" },
      ),
    );

    await waitFor(() => {
      expect(submittedBody).toBeDefined();
    });

    expect(
      String(
        submittedBody?.client_request_id,
      ),
    ).toMatch(/^reversal-/);

    expect(
      Object.keys(
        submittedBody ?? {},
      ),
    ).toEqual([
      "client_request_id",
    ]);

    await waitFor(() => {
      expect(
        screen.queryByRole(
          "dialog",
          {
            name:
              "Отменить операцию № 42?",
          },
        ),
      ).not.toBeInTheDocument();
    });
  },
);

it(
  "не предлагает CORRECTION для custody movement, но сохраняет REVERSAL",
  () => {
    renderActions(
      [
        "catalog.read",
        "inventory.read",
        "inventory.admin",
        "movement.read_all",
      ],
      {
        ...movement,
        movement_type: "ISSUE",
        custody_user_id: "user-2",
        source_location_id:
          "location-1",
        destination_location_id: null,
        source_location_name_snapshot:
          "Основной склад",
        destination_location_name_snapshot:
          null,
      },
    );

    expect(
      screen.queryByRole(
        "button",
        { name: "Корректировать остаток" },
      ),
    ).not.toBeInTheDocument();

    expect(
      screen.getByRole(
        "button",
        { name: "Отменить операцию" },
      ),
    ).toBeInTheDocument();
  },
);
