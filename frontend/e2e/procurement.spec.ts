import {
  expect,
  type Page,
  type Route,
  test,
} from "@playwright/test";

const now = "2026-09-12T12:00:00Z";
const requestId = "request-1";
const revisionId = "revision-1";
const managerId = "user-manager";
const locationId = "location-1";

type MockRole =
  | "SENIOR_ENGINEER"
  | "MANAGER";

type ProcurementStatus =
  | "AGREEMENT_PENDING_MANAGER"
  | "AGREEMENT_REVISION_REQUIRED"
  | "PURCHASING"
  | "AWAITING_ACCEPTANCE"
  | "COMPLETED";

type ProcurementRequest = {
  id: string;
  request_number: string;
  status: ProcurementStatus;
  status_label: string;
  initiator: {
    id: string;
    display_name: string;
  };
  assigned_manager: {
    id: string;
    display_name: string;
  };
  current_revision_id: string;
  revision_number: number;
  line_count: number;
  state_version: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  current_revision: {
    id: string;
    revision_number: number;
    submitted_by: {
      id: string;
      display_name: string;
    };
    general_comment: string | null;
    created_at: string;
    lines: Array<{
      id: string;
      line_no: number;
      line_type: "EXISTING_ITEM" | "PROPOSED_ITEM";
      catalog_item_id: string | null;
      bound_item_id: string | null;
      display_snapshot: Record<string, unknown>;
      quantity: number;
    }>;
  };
  revisions: ProcurementRequest["current_revision"][];
  events: Array<{
    id: string;
    event_type: string;
    actor: {
      id: string;
      display_name: string;
    };
    from_status: ProcurementStatus | null;
    to_status: ProcurementStatus | null;
    revision_id: string | null;
    comment: string | null;
    metadata: Record<string, unknown> | null;
    occurred_at: string;
  }>;
  final_movement_id: string | null;
  available_actions: string[];
};

function capabilities(role: MockRole): string[] {
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
    "catalog.archive",
    "catalog.delete_unused",
    "inventory.read",
    "inventory.operate",
    "movement.read_own",
    "movement.read_all",
    "procurement.read",
    "procurement.accept",
  ];
}

function json(
  route: Route,
  body: unknown,
  status = 200,
) {
  return route.fulfill({
    json: body,
    status,
  });
}

async function installTelegramMock(page: Page) {
  await page.route(
    "**/vendor/telegram/telegram-web-app.js",
    (route) =>
      route.fulfill({
        body: "",
        contentType: "application/javascript",
      }),
  );

  await page.addInitScript(() => {
    Object.defineProperty(window, "Telegram", {
      configurable: true,
      value: {
        WebApp: {
          initData: "synthetic-signed-data",
          platform: "tdesktop",
          ready: () => undefined,
          expand: () => undefined,
          onEvent: () => undefined,
          offEvent: () => undefined,
          BackButton: {
            show: () => undefined,
            hide: () => undefined,
            onClick: () => undefined,
            offClick: () => undefined,
          },
        },
      },
    });
  });
}

function makeRequest(
  status: ProcurementStatus,
  statusLabel: string,
  actions: string[],
): ProcurementRequest {
  const revision: ProcurementRequest["current_revision"] = {
    id: revisionId,
    revision_number: 1,
    submitted_by: {
      id: "user-admin",
      display_name: "Администратор",
    },
    general_comment: null,
    created_at: now,
    lines: [
      {
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
      },
    ],
  };

  return {
    id: requestId,
    request_number: "PR-2026-0001",
    status,
    status_label: statusLabel,
    initiator: {
      id: "user-admin",
      display_name: "Администратор",
    },
    assigned_manager: {
      id: managerId,
      display_name: "Менеджер",
    },
    current_revision_id: revisionId,
    revision_number: 1,
    line_count: 1,
    state_version: 7,
    created_at: now,
    updated_at: now,
    completed_at: null,
    current_revision: revision,
    revisions: [revision],
    events: [],
    final_movement_id: null,
    available_actions: actions,
  };
}

async function installProcurementApiMock(
  page: Page,
  role: MockRole,
  initialRequest: ProcurementRequest,
) {
  let current = structuredClone(initialRequest);

  const requests: string[] = [];
  const mutations: Array<{
    action: string;
    body: Record<string, unknown>;
  }> = [];

  await page.route(
    /^https?:\/\/[^/]+\/api\//,
    async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;
      const method = request.method();

      requests.push(`${method} ${path}${url.search}`);

      if (
        path === "/api/auth/me"
        || path === "/api/auth/telegram"
      ) {
        return json(route, {
          user: {
            id:
              role === "MANAGER"
                ? managerId
                : "user-senior",
            telegram_user_id: 1001,
            first_name:
              role === "MANAGER"
                ? "Менеджер"
                : "Старший инженер",
            last_name: null,
            username: role.toLowerCase(),
            role,
            capabilities: capabilities(role),
            access_status: "APPROVED",
          },
          support: {
            username: "support",
            url: "https://t.me/support",
          },
        });
      }

      if (
        path === "/api/procurement/requests"
        && method === "GET"
      ) {
        return json(route, {
          items: [
            {
              id: current.id,
              request_number: current.request_number,
              status: current.status,
              status_label: current.status_label,
              initiator: current.initiator,
              assigned_manager: current.assigned_manager,
              current_revision_id:
                current.current_revision_id,
              revision_number: current.revision_number,
              line_count: current.line_count,
              state_version: current.state_version,
              created_at: current.created_at,
              updated_at: current.updated_at,
              completed_at: current.completed_at,
            },
          ],
          total: 1,
          limit: 30,
          offset: 0,
        });
      }

      if (
        path
          === `/api/procurement/requests/${requestId}`
        && method === "GET"
      ) {
        return json(route, current);
      }

      if (
        path === "/api/procurement/managers"
        && method === "GET"
      ) {
        return json(route, {
          items: [
            {
              id: managerId,
              display_name: "Менеджер",
            },
            {
              id: "user-manager-2",
              display_name: "Второй менеджер",
            },
          ],
          total: 2,
          limit: 200,
          offset: 0,
        });
      }

      if (
        path === "/api/inventory/locations"
        && method === "GET"
      ) {
        return json(route, {
          items: [
            {
              id: locationId,
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

      const actionMatch = path.match(
        /^\/api\/procurement\/requests\/request-1\/([^/]+)$/,
      );

      if (
        actionMatch
        && method === "POST"
      ) {
        const action = actionMatch[1];
        const body =
          request.postDataJSON() as Record<
            string,
            unknown
          >;

        mutations.push({
          action,
          body,
        });

        if (action === "acceptance") {
          current = {
            ...current,
            status: "COMPLETED",
            status_label: "Завершена",
            state_version:
              current.state_version + 1,
            completed_at: now,
            final_movement_id: "movement-1",
            available_actions: [],
          };

          return json(route, current);
        }

        if (action === "return-for-correction") {
          current = {
            ...current,
            status: "AGREEMENT_REVISION_REQUIRED",
            status_label: "Требуется корректировка",
            state_version:
              current.state_version + 1,
            available_actions: [
              "transfer_manager",
            ],
            events: [
              ...current.events,
              {
                id: "event-correction",
                event_type: "CORRECTION_REQUESTED",
                actor: {
                  id: managerId,
                  display_name: "Менеджер",
                },
                from_status:
                  "AGREEMENT_PENDING_MANAGER",
                to_status:
                  "AGREEMENT_REVISION_REQUIRED",
                revision_id: revisionId,
                comment:
                  String(body.comment ?? ""),
                metadata: null,
                occurred_at: now,
              },
            ],
          };

          return json(route, current);
        }

        if (action === "discrepancies") {
          current = {
            ...current,
            state_version:
              current.state_version + 1,
            events: [
              ...current.events,
              {
                id: "event-discrepancy",
                event_type: "DISCREPANCY_REPORTED",
                actor: {
                  id: "user-senior",
                  display_name: "Старший инженер",
                },
                from_status:
                  "AWAITING_ACCEPTANCE",
                to_status:
                  "AWAITING_ACCEPTANCE",
                revision_id: revisionId,
                comment:
                  String(body.comment ?? ""),
                metadata: null,
                occurred_at: now,
              },
            ],
          };

          return json(route, current);
        }
      }

      return json(
        route,
        {
          detail:
            `Unhandled route ${method} ${path}`,
        },
        500,
      );
    },
  );

  return {
    requests,
    mutations,
    current: () => current,
  };
}

test(
  "SENIOR completes technical acceptance from procurement queue",
  async ({ page }) => {
    await installTelegramMock(page);

    const api = await installProcurementApiMock(
      page,
      "SENIOR_ENGINEER",
      makeRequest(
        "AWAITING_ACCEPTANCE",
        "Ожидает приёмки",
        [
          "report_discrepancy",
          "complete_acceptance",
        ],
      ),
    );

    await page.goto("/procurement");

    await expect(
      page.getByRole(
        "heading",
        { name: "Закупки" },
      ),
    ).toBeVisible();

    await page.getByRole(
      "link",
      { name: /PR-2026-0001/ },
    ).click();

    await expect(page).toHaveURL(
      /\/procurement\/request-1$/,
    );

    await page.getByRole(
      "button",
      { name: "Подтвердить приёмку" },
    ).click();

    const dialog = page.getByRole(
      "dialog",
      { name: "Подтвердить приёмку" },
    );

    await expect(dialog).toContainText(
      "SFP-25G-SR",
    );
    await expect(dialog).toContainText(
      "4 шт.",
    );

    const confirm = page.getByRole(
      "button",
      {
        name: "Подтвердить и оприходовать",
      },
    );

    await expect(confirm).toBeDisabled();

    await page.getByLabel(
      "Место приёмки",
    ).selectOption(locationId);

    await expect(confirm).toBeEnabled();

    await confirm.click();

    await expect(
      page.getByText(
        "Завершена",
        { exact: true },
      ),
    ).toBeVisible();

    await expect(
      page.getByRole(
        "link",
        { name: "Открыть складской приход" },
      ),
    ).toBeVisible();

    await expect.poll(
      () =>
        api.mutations.filter(
          (entry) =>
            entry.action === "acceptance",
        ).length,
    ).toBe(1);

    const acceptance =
      api.mutations.find(
        (entry) =>
          entry.action === "acceptance",
      );

    expect(acceptance?.body).toMatchObject({
      expected_state_version: 7,
      expected_revision_id: revisionId,
      receiving_location_id: locationId,
    });

    expect(
      typeof acceptance?.body.client_request_id,
    ).toBe("string");
  },
);

test(
  "MANAGER returns request for correction with mandatory comment",
  async ({ page }) => {
    await installTelegramMock(page);

    const api = await installProcurementApiMock(
      page,
      "MANAGER",
      makeRequest(
        "AGREEMENT_PENDING_MANAGER",
        "На согласовании у менеджера",
        [
          "transfer_manager",
          "manager_accept",
          "return_for_correction",
        ],
      ),
    );

    await page.goto("/procurement");

    await expect(
      page.getByRole(
        "tab",
        { name: "Мои" },
      ),
    ).toHaveAttribute(
      "aria-selected",
      "true",
    );

    await page.getByRole(
      "link",
      { name: /PR-2026-0001/ },
    ).click();

    await page.getByRole(
      "button",
      { name: "Вернуть на корректировку" },
    ).click();

    const submit = page.getByRole(
      "button",
      { name: "Вернуть", exact: true },
    );

    await expect(submit).toBeDisabled();

    await page.getByLabel(
      "Комментарий",
    ).fill(
      "Нужно скорректировать количество",
    );

    await expect(submit).toBeEnabled();

    await submit.click();

    await expect(
      page.getByText(
        "Требуется корректировка",
        { exact: true },
      ),
    ).toBeVisible();

    const correction =
      api.mutations.find(
        (entry) =>
          entry.action
          === "return-for-correction",
      );

    expect(correction?.body).toMatchObject({
      comment:
        "Нужно скорректировать количество",
      alternative_proposal: null,
      expected_state_version: 7,
      expected_revision_id: revisionId,
    });

    expect(
      api.requests.some(
        (entry) =>
          entry.includes(
            "/api/inventory/movements",
          ),
      ),
    ).toBe(false);
  },
);

test(
  "SENIOR reports discrepancy without warehouse mutation",
  async ({ page }) => {
    await installTelegramMock(page);

    const api = await installProcurementApiMock(
      page,
      "SENIOR_ENGINEER",
      makeRequest(
        "AWAITING_ACCEPTANCE",
        "Ожидает приёмки",
        [
          "report_discrepancy",
          "complete_acceptance",
        ],
      ),
    );

    await page.goto(
      `/procurement/${requestId}`,
    );

    await page.getByRole(
      "button",
      { name: "Есть расхождения" },
    ).click();

    const submit = page.getByRole(
      "button",
      { name: "Зафиксировать" },
    );

    await expect(submit).toBeDisabled();

    await page.getByLabel(
      "Что отличается",
    ).fill(
      "Фактически получено другое исполнение",
    );

    await expect(submit).toBeEnabled();

    await submit.click();

    await expect(
      page.getByText(
        "Фактически получено другое исполнение",
      ),
    ).toBeVisible();

    expect(
      api.current().status,
    ).toBe("AWAITING_ACCEPTANCE");

    expect(
      api.current().final_movement_id,
    ).toBeNull();

    const discrepancy =
      api.mutations.find(
        (entry) =>
          entry.action === "discrepancies",
      );

    expect(discrepancy?.body).toMatchObject({
      comment:
        "Фактически получено другое исполнение",
      expected_state_version: 7,
      expected_revision_id: revisionId,
    });

    expect(
      api.mutations.some(
        (entry) =>
          entry.action === "acceptance",
      ),
    ).toBe(false);

    expect(
      api.requests.some(
        (entry) =>
          entry.includes(
            "/api/inventory/movements",
          ),
      ),
    ).toBe(false);
  },
);
