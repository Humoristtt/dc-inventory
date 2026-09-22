import { expect, type Page, type Route, test } from "@playwright/test";

const users = [
  {
    id: "user-engineer",
    telegram_user_id: 10101,
    username: "engineer_demo",
    first_name: "Алексей",
    last_name: "Петров",
    role: "ENGINEER",
    access_status: "APPROVED",
    created_at: "2026-09-01T12:00:00Z",
    updated_at: "2026-09-01T12:00:00Z",
    approved_at: "2026-09-01T12:00:00Z",
    is_recovery_identity: false,
  },
  {
    id: "user-manager",
    telegram_user_id: 20202,
    username: "manager_demo",
    first_name: "Мария",
    last_name: "Соколова",
    role: "MANAGER",
    access_status: "BLOCKED",
    created_at: "2026-09-01T12:00:00Z",
    updated_at: "2026-09-01T12:00:00Z",
    approved_at: "2026-09-01T12:00:00Z",
    is_recovery_identity: false,
  },
];

async function prepareApp(page: Page) {
  await page.addInitScript(() => {
    Object.defineProperty(window, "Telegram", {
      configurable: true,
      value: {
        WebApp: {
          initData: "synthetic-test-data",
          platform: "tdesktop",
          isFullscreen: false,
          ready: () => undefined,
          expand: () => undefined,
          requestFullscreen: () => undefined,
          exitFullscreen: () => undefined,
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

  await page.route(/^https?:\/\/[^/]+\/api\//, (route: Route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me") {
      return route.fulfill({ json: {
        user: {
          id: "owner-demo",
          telegram_user_id: 99999,
          username: "owner_demo",
          first_name: "Владелец",
          last_name: null,
          role: "OWNER",
          capabilities: [
            "catalog.read",
            "inventory.read",
            "access.manage_users",
            "access.assign_standard_roles",
            "access.assign_admin",
          ],
          access_status: "APPROVED",
        },
        support: { username: "support", url: "https://t.me/support" },
      } });
    }
    if (path === "/api/admin/users") {
      return route.fulfill({ json: { items: users, total: users.length } });
    }
    return route.fulfill({ json: {} });
  });
}

test("admin user cards are legible, styled and responsive", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-admin", "Desktop and narrow layout contract");
  await prepareApp(page);
  await page.goto("/more/users");

  const cards = page.locator(".admin-user-card");
  await expect(cards).toHaveCount(2);
  await expect(page.getByText("Доступ разрешён", { exact: true })).toBeVisible();
  await expect(page.getByText("Заблокирован", { exact: true })).toBeVisible();

  for (const width of [390, 1280, 1920]) {
    await page.setViewportSize({ width, height: 900 });

    const metrics = await page.evaluate(() => {
      const userCards = [...document.querySelectorAll<HTMLElement>(".admin-user-card")];
      const first = userCards[0];
      const second = userCards[1];
      const status = first?.querySelector<HTMLElement>(".admin-user-card__status");
      const role = first?.querySelector<HTMLSelectElement>("select");
      const block = first?.querySelector<HTMLButtonElement>(".button--danger");
      if (!first || !second || !status || !role || !block) return null;
      return {
        first: first.getBoundingClientRect().toJSON(),
        second: second.getBoundingClientRect().toJSON(),
        statusFont: Number.parseFloat(getComputedStyle(status).fontSize),
        statusHeight: status.getBoundingClientRect().height,
        selectHeight: role.getBoundingClientRect().height,
        selectAppearance: getComputedStyle(role).appearance,
        selectBackground: getComputedStyle(role).backgroundImage,
        blockBackground: getComputedStyle(block).backgroundColor,
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
      };
    });

    expect(metrics).not.toBeNull();
    if (metrics === null) throw new Error("Admin card layout unavailable");
    expect(metrics.statusFont).toBeGreaterThanOrEqual(13);
    expect(metrics.statusHeight).toBeGreaterThanOrEqual(36);
    expect(metrics.selectHeight).toBeGreaterThanOrEqual(48);
    expect(metrics.selectAppearance).toBe("none");
    expect(metrics.selectBackground).not.toBe("none");
    expect(metrics.blockBackground).not.toBe("rgb(255, 0, 0)");
    expect(metrics.documentWidth).toBeLessThanOrEqual(metrics.viewportWidth + 1);

    if (width >= 1920) {
      expect(Math.abs(metrics.first.top - metrics.second.top)).toBeLessThanOrEqual(2);
      expect(metrics.second.left).toBeGreaterThan(metrics.first.right);
    } else {
      expect(metrics.second.top).toBeGreaterThanOrEqual(metrics.first.bottom);
    }
  }
});
