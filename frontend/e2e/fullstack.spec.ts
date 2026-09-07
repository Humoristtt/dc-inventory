import { createHmac } from "node:crypto";

import {
  expect,
  type Page,
  test,
} from "@playwright/test";


const botToken =
  process.env.FULLSTACK_TELEGRAM_BOT_TOKEN?.trim() ?? "";

const telegramUserId = Number(
  process.env.FULLSTACK_TELEGRAM_USER_ID ?? "42424242",
);


function createSignedTelegramInitData(): string {
  if (botToken === "") {
    throw new Error(
      "FULLSTACK_TELEGRAM_BOT_TOKEN is required",
    );
  }

  if (
    !Number.isSafeInteger(telegramUserId)
    || telegramUserId <= 0
  ) {
    throw new Error(
      "FULLSTACK_TELEGRAM_USER_ID must be a positive safe integer",
    );
  }

  const fields: Record<string, string> = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    query_id: "fullstack-ci-query",
    user: JSON.stringify({
      id: telegramUserId,
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
    expect(authBody.user.role).toBe("ADMIN");
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
  },
);
