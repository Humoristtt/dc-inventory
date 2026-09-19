import { createHmac, randomUUID } from "node:crypto";

import {
  expect,
  type APIRequestContext,
  type Page,
  test,
} from "@playwright/test";


const botToken =
  process.env.FULLSTACK_TELEGRAM_BOT_TOKEN?.trim() ?? "";

const telegramUserId = Number(
  process.env.FULLSTACK_TELEGRAM_USER_ID ?? "42424242",
);


function createSignedTelegramInitData(userId = telegramUserId): string {
  if (botToken === "") {
    throw new Error(
      "FULLSTACK_TELEGRAM_BOT_TOKEN is required",
    );
  }

  if (!Number.isSafeInteger(userId) || userId <= 0) {
    throw new Error(
      "FULLSTACK_TELEGRAM_USER_ID must be a positive safe integer",
    );
  }

  const fields: Record<string, string> = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    query_id: "fullstack-ci-query",
    user: JSON.stringify({
      id: userId,
      first_name: "Fullstack",
      last_name: "CI",
      username: "dc_inventory_fullstack_ci",
      language_code: "en",
    }),
  };

  const dataCheckString = Object.entries(fields)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`)
    .join("\n");

  const secretKey = createHmac(
    "sha256",
    "WebAppData",
  )
    .update(botToken)
    .digest();

  const hash = createHmac(
    "sha256",
    secretKey,
  )
    .update(dataCheckString)
    .digest("hex");

  return new URLSearchParams({
    ...fields,
    hash,
  }).toString();
}


async function installTelegramContext(
  page: Page,
  initData: string,
): Promise<void> {
  await page.addInitScript((signedInitData: string) => {
    const backButton = {
      show: () => undefined,
      hide: () => undefined,
      onClick: () => undefined,
      offClick: () => undefined,
    };

    Object.defineProperty(window, "Telegram", {
      configurable: true,
      value: {
        WebApp: {
          initData: signedInitData,
          platform: "tdesktop",
          ready: () => undefined,
          expand: () => undefined,
          onEvent: () => undefined,
          offEvent: () => undefined,
          BackButton: backButton,
        },
      },
    });
  }, initData);
}


test(
  "signed Telegram admin traverses real frontend API and database",
  async ({ page }) => {
    const initData = createSignedTelegramInitData();

    await installTelegramContext(page, initData);

    const authentication = page.waitForResponse(
      (response) => (
        response.url().endsWith("/api/auth/telegram")
        && response.request().method() === "POST"
      ),
    );

    const catalog = page.waitForResponse(
      (response) => (
        response.url().endsWith("/api/catalog/categories")
        && response.request().method() === "GET"
      ),
    );

    await page.goto("/catalog");

    const authResponse = await authentication;

    expect(authResponse.status()).toBe(200);

    const authBody = await authResponse.json() as {
      user: {
        telegram_user_id: number;
        role: string;
        access_status: string;
      };
    };

    expect(authBody.user.telegram_user_id)
      .toBe(telegramUserId);
    expect(authBody.user.role).toBe("OWNER");
    expect(authBody.user.access_status).toBe("APPROVED");

    const catalogResponse = await catalog;

    expect(catalogResponse.status()).toBe(200);

    const categories = await catalogResponse.json() as Array<{
      key: string;
    }>;

    expect(categories.length).toBeGreaterThan(0);
    expect(
      categories.some((category) => category.key === "transceiver_ethernet"),
    ).toBe(true);

    await expect(
      page.getByRole(
        "heading",
        { name: "Найти оборудование" },
      ),
    ).toBeVisible();

    // Real warehouse route -> backend -> isolated PostgreSQL.
    const locationsRequest = page.waitForResponse(
      (response) => (
        new URL(response.url()).pathname === "/api/inventory/locations"
        && response.request().method() === "GET"
      ),
    );

    await page.goto("/more/locations");

    const locationsResponse = await locationsRequest;
    expect(locationsResponse.status()).toBe(200);

    const locationsBody = await locationsResponse.json() as {
      items: unknown[];
      total: number;
    };

    expect(Array.isArray(locationsBody.items)).toBe(true);
    expect(Number.isInteger(locationsBody.total)).toBe(true);
    await expect(page.getByRole("heading", { name: "Места хранения" }))
      .toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);

    // Real procurement route -> backend -> isolated PostgreSQL.
    const procurementRequest = page.waitForResponse(
      (response) => (
        new URL(response.url()).pathname === "/api/procurement/requests"
        && response.request().method() === "GET"
      ),
    );

    await page.goto("/procurement");

    const procurementResponse = await procurementRequest;
    expect(procurementResponse.status()).toBe(200);

    const procurementBody = await procurementResponse.json() as {
      items: unknown[];
      total: number;
    };

    expect(Array.isArray(procurementBody.items)).toBe(true);
    expect(Number.isInteger(procurementBody.total)).toBe(true);
    await expect(page.getByRole("heading", { name: "Закупки" }))
      .toBeVisible();
    await expect(page.getByRole("tablist", { name: "Очередь закупок" }))
      .toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  },
);

test("isolated HTTP acceptance covers RBAC, warehouse and procurement", async ({ playwright }) => {
  test.skip(
    process.env.FULLSTACK_MUTATIONS_ENABLED !== "true",
    "mutations require the disposable-database runner",
  );
  const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173";
  const contexts: APIRequestContext[] = [];

  async function context(userId: number): Promise<{
    api: APIRequestContext;
    user: { id: string; role: string; access_status: string };
  }> {
    const api = await playwright.request.newContext({
      baseURL,
      extraHTTPHeaders: { Origin: baseURL },
    });
    contexts.push(api);
    const response = await api.post("/api/auth/telegram", {
      data: { init_data: createSignedTelegramInitData(userId) },
    });
    expect(response.status()).toBe(200);
    const body = await response.json() as {
      user: { id: string; role: string; access_status: string };
    };
    return { api, user: body.user };
  }

  async function post(
    api: APIRequestContext,
    path: string,
    data: object,
    status = 200,
  ): Promise<Record<string, any>> {
    const response = await api.post(path, { data });
    expect(response.status(), `${path}: ${await response.text()}`).toBe(status);
    return await response.json() as Record<string, any>;
  }

  try {
    const owner = await context(telegramUserId);
    const admin = await context(42424244);
    const engineer = await context(42424245);
    const manager = await context(42424246);
    const senior = await context(42424247);
    expect(owner.user).toMatchObject({ role: "OWNER", access_status: "APPROVED" });
    expect(admin.user.access_status).toBe("PENDING");

    const anonymous = await playwright.request.newContext({ baseURL });
    contexts.push(anonymous);
    expect((await anonymous.get("/api/inventory/locations")).status()).toBe(401);
    expect((await admin.api.get("/api/catalog/categories")).status()).toBe(403);
    expect((await anonymous.post("/api/auth/telegram", {
      data: { init_data: "invalid" },
    })).status()).toBe(401);

    for (const target of [admin, engineer, manager, senior]) {
      const access = await post(target.api, "/api/access-requests", {}, 200);
      expect(access.request.status).toBe("PENDING");
      const approved = await post(
        owner.api,
        `/api/admin/users/${target.user.id}/access-request-decision`,
        { decision: "APPROVE" },
      );
      expect(approved.access_status).toBe("APPROVED");
    }

    for (const [target, role] of [
      [admin, "ADMIN"],
      [manager, "MANAGER"],
      [senior, "SENIOR_ENGINEER"],
    ] as const) {
      const response = await owner.api.patch(`/api/admin/users/${target.user.id}/role`, {
        data: { role },
      });
      expect(response.status()).toBe(200);
      expect((await response.json() as { role: string }).role).toBe(role);
    }
    expect((await admin.api.patch(`/api/admin/users/${engineer.user.id}/role`, {
      data: { role: "ADMIN" },
    })).status()).toBe(403);
    expect((await engineer.api.get("/api/admin/users")).status()).toBe(403);
    expect((await engineer.api.get("/api/procurement/requests")).status()).toBe(403);
    expect((await manager.api.post("/api/inventory/movements", {
      data: { movement_type: "RECEIPT", client_request_id: randomUUID(), lines: [] },
    })).status()).toBe(403);

    const code = `CP14-${randomUUID().slice(0, 8)}`;
    const location = await post(owner.api, "/api/admin/inventory/locations", {
      code, name: "CP14 склад", location_type: "WAREHOUSE",
    }, 201);
    const destination = await post(admin.api, "/api/admin/inventory/locations", {
      code: `${code}-B`, name: "CP14 ЦОД", location_type: "DATACENTER",
    }, 201);
    const item = await post(owner.api, "/api/admin/catalog/items", {
      category_key: "optical_patch_cord",
      name: `CP14 synthetic cable ${code}`,
      attributes: {
        fiber: "MMF", fiber_category: "OM4", connector_a: "LC/UPC",
        connector_b: "LC/UPC", length_m: "5", construction: "Duplex",
        color: code,
      },
    }, 201);
    const line = [{ item_id: item.id, quantity: 10 }];
    const receiptPayload = {
      movement_type: "RECEIPT", destination_location_id: location.id,
      client_request_id: randomUUID(), lines: line,
    };
    const receipt = await post(owner.api, "/api/inventory/movements", receiptPayload, 201);
    const receiptReplay = await post(owner.api, "/api/inventory/movements", receiptPayload, 201);
    expect(receiptReplay.id).toBe(receipt.id);
    const issue = await post(engineer.api, "/api/inventory/movements", {
      movement_type: "ISSUE", source_location_id: location.id,
      client_request_id: randomUUID(), lines: [{ item_id: item.id, quantity: 3 }],
    }, 201);
    expect(issue.custody_user_id).toBe(engineer.user.id);
    await post(engineer.api, "/api/inventory/movements", {
      movement_type: "RETURN", destination_location_id: location.id,
      client_request_id: randomUUID(), lines: [{ item_id: item.id, quantity: 1 }],
    }, 201);
    await post(admin.api, "/api/inventory/movements", {
      movement_type: "TRANSFER", source_location_id: location.id,
      destination_location_id: destination.id, client_request_id: randomUUID(),
      lines: [{ item_id: item.id, quantity: 2 }],
    }, 201);
    expect((await engineer.api.post("/api/inventory/movements", {
      data: {
        movement_type: "ISSUE", source_location_id: location.id,
        client_request_id: randomUUID(), lines: [{ item_id: item.id, quantity: 100 }],
      },
    })).status()).toBe(409);
    const summaryResponse = await owner.api.get(`/api/inventory/items/${item.id}/summary`);
    expect(summaryResponse.status()).toBe(200);
    expect((await summaryResponse.json() as { total_count: number }).total_count).toBe(8);
    const historyResponse = await owner.api.get("/api/inventory/movements?period=all");
    expect(historyResponse.status()).toBe(200);
    expect((await historyResponse.json() as { items: unknown[] }).items).toHaveLength(4);
    expect((await engineer.api.get(`/api/inventory/movements/${receipt.id}`)).status()).toBe(403);

    const requestPayload = {
      assigned_manager_user_id: manager.user.id,
      general_comment: "CP14 synthetic procurement",
      client_request_id: randomUUID(),
      lines: [{ line_type: "EXISTING_ITEM", item_id: item.id, quantity: 4 }],
    };
    let procurement = await post(owner.api, "/api/procurement/requests", requestPayload, 201);
    const requestReplay = await post(owner.api, "/api/procurement/requests", requestPayload, 201);
    expect(requestReplay.id).toBe(procurement.id);
    const path = `/api/procurement/requests/${procurement.id}`;
    const expected = () => ({
      expected_state_version: procurement.state_version,
      expected_revision_id: procurement.current_revision_id,
      client_request_id: randomUUID(),
    });
    expect((await engineer.api.post(`${path}/manager-accept`, {
      data: expected(),
    })).status()).toBe(403);
    procurement = await post(manager.api, `${path}/return-for-correction`, {
      ...expected(), comment: "Уточнить количество",
    });
    expect(procurement.status).toBe("AGREEMENT_REVISION_REQUIRED");
    procurement = await post(owner.api, `${path}/revisions`, {
      ...expected(), general_comment: "CP14 revised",
      lines: [{ line_type: "EXISTING_ITEM", item_id: item.id, quantity: 4 }],
    });
    expect(procurement.revisions).toHaveLength(2);
    procurement = await post(manager.api, `${path}/manager-accept`, expected());
    expect(procurement.status).toBe("PURCHASING");
    procurement = await post(manager.api, `${path}/transfer-to-acceptance`, expected());
    expect(procurement.status).toBe("AWAITING_ACCEPTANCE");
    expect((await manager.api.post(`${path}/acceptance`, {
      data: { ...expected(), receiving_location_id: location.id },
    })).status()).toBe(403);
    const acceptancePayload = { ...expected(), receiving_location_id: location.id };
    procurement = await post(senior.api, `${path}/acceptance`, acceptancePayload);
    expect(procurement.status).toBe("COMPLETED");
    expect(procurement.final_movement_id).toBeTruthy();
    const acceptedReplay = await post(senior.api, `${path}/acceptance`, acceptancePayload);
    expect(acceptedReplay.final_movement_id).toBe(procurement.final_movement_id);
    expect(procurement.events.length).toBeGreaterThanOrEqual(6);
    const finalSummary = await owner.api.get(`/api/inventory/items/${item.id}/summary`);
    expect(finalSummary.status()).toBe(200);
    expect((await finalSummary.json() as { total_count: number }).total_count).toBe(12);
    expect((await owner.api.post(`/api/admin/inventory/movements/${procurement.final_movement_id}/reversal`, {
      data: { client_request_id: randomUUID() },
    })).status()).toBe(409);
  } finally {
    await Promise.all(contexts.map((api) => api.dispose()));
  }
});
