import { expect, type Page, type Route, test } from "@playwright/test";

const family = {
  id: "family",
  key: "transceivers",
  display_name: "Трансиверы",
  description: "Оптические трансиверы",
  parent_id: null,
  sort_order: 0,
  is_system: true,
};

const category = {
  id: "leaf",
  key: "transceiver_ethernet",
  display_name: "Ethernet",
  description: null,
  parent_id: family.id,
  sort_order: 0,
  is_system: true,
};

function respond(route: Route, body: unknown) {
  return route.fulfill({ json: body });
}

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

  await page.route(/^https?:\/\/[^/]+\/api\//, (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me") {
      return respond(route, {
        user: {
          id: "00000000-0000-4000-8000-000000000111",
          telegram_user_id: 1001,
          first_name: "Тест",
          last_name: null,
          username: "responsive_test",
          role: "OWNER",
          capabilities: ["catalog.read", "catalog.manage", "inventory.read"],
          access_status: "APPROVED",
        },
        support: { username: "support", url: "https://t.me/support" },
      });
    }
    if (path === "/api/catalog/categories") {
      return respond(route, [family, category]);
    }
    if (path.startsWith("/api/catalog/categories/")) {
      return respond(
        route,
        path.endsWith("transceivers")
          ? { ...family, attributes: [] }
          : { ...category, attributes: [] },
      );
    }
    if (path === "/api/catalog/items") {
      return respond(route, { items: [], total: 0, limit: 20, offset: 0 });
    }
    if (path === "/api/catalog/items/facets") {
      return respond(route, {
        facets: [{
          key: "availability",
          label: "Наличие",
          data_type: "ENUM",
          filter_type: "EXACT",
          values: [
            { value: "IN_STOCK", label: "В наличии", count: 1 },
            { value: "OUT_OF_STOCK", label: "Нет в наличии", count: 1 },
          ],
          min: null,
          max: null,
        }],
      });
    }
    return respond(route, {});
  });
}

async function expectNoHorizontalOverflow(page: Page) {
  await expect.poll(() => page.evaluate(() => (
    document.documentElement.scrollWidth <= window.innerWidth + 1
    && document.body.scrollWidth <= window.innerWidth + 1
  ))).toBe(true);
}

test("catalog uses content width rather than a fixed device-size layout", async ({ page }, testInfo) => {
  test.skip(
    !["desktop-admin", "iphone-webkit"].includes(testInfo.project.name),
    "Representative desktop and WebKit acceptance",
  );
  await prepareApp(page);
  await page.goto("/catalog");
  const grid = page.locator(".category-grid");
  await expect(grid).toBeVisible();

  for (const [width, expectedColumns] of [
    [320, 2],
    [390, 2],
    [600, 2],
    [768, 3],
    [1024, 3],
    [1280, 4],
    [1920, 4],
    [2560, 4],
  ] as const) {
    await page.setViewportSize({ width, height: width <= 390 ? 420 : 900 });
    await expect.poll(() => grid.evaluate((element) => (
      getComputedStyle(element)
        .gridTemplateColumns
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .length
    ))).toBe(expectedColumns);
    await expectNoHorizontalOverflow(page);

    const fitsNavigation = await page.evaluate(() => {
      const content = document.querySelector<HTMLElement>(".app-shell__content");
      const nav = document.querySelector<HTMLElement>(".bottom-nav");
      if (content === null || nav === null) return false;
      const body = content.getBoundingClientRect();
      const footer = nav.getBoundingClientRect();
      return window.innerWidth >= 1200
        ? Math.abs(body.bottom - footer.top) <= 2
        : Number.parseFloat(getComputedStyle(content).paddingBottom) >= footer.height;
    });
    expect(fitsNavigation).toBe(true);
  }
});

test("wide desktop menu occupies a separate bottom row and never covers cards", async ({ page }, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop-admin",
    "Desktop viewport geometry acceptance",
  );

  await prepareApp(page);
  await page.goto("/catalog");
  await expect(page.locator(".category-grid")).toBeVisible();

  for (const width of [1280, 1920, 2560]) {
    await page.setViewportSize({ width, height: 900 });
    await page.locator(".catalog-page__body").evaluate((body) => {
      (body as HTMLElement).style.minHeight = "1800px";
    });
    await page.locator(".app-shell__content").evaluate((content) => {
      content.scrollTop = 500;
    });

    const geometry = await page.evaluate(() => {
      const content = document.querySelector<HTMLElement>(".app-shell__content");
      const nav = document.querySelector<HTMLElement>(".bottom-nav");
      const links = document.querySelector<HTMLElement>(".bottom-nav__inner");
      if (content === null || nav === null || links === null) return null;

      const contentRect = content.getBoundingClientRect();
      const navRect = nav.getBoundingClientRect();
      const linksRect = links.getBoundingClientRect();
      return {
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        contentLeft: contentRect.left,
        contentRight: contentRect.right,
        contentBottom: contentRect.bottom,
        navLeft: navRect.left,
        navRight: navRect.right,
        navTop: navRect.top,
        navBottom: navRect.bottom,
        linksLeft: linksRect.left,
        linksRight: linksRect.right,
        scrollTop: content.scrollTop,
        position: getComputedStyle(nav).position,
        background: getComputedStyle(nav).backgroundColor,
      };
    });

    expect(geometry).not.toBeNull();
    if (geometry === null) throw new Error("Desktop navigation geometry unavailable");

    expect(geometry.position).toBe("relative");
    expect(geometry.scrollTop).toBeGreaterThan(0);
    expect(geometry.background).toBe("rgb(7, 6, 4)");
    expect(Math.abs(geometry.contentBottom - geometry.navTop)).toBeLessThanOrEqual(2);
    expect(Math.abs(geometry.navBottom - geometry.viewportHeight)).toBeLessThanOrEqual(2);
    expect(Math.abs(geometry.contentLeft)).toBeLessThanOrEqual(1);
    expect(Math.abs(geometry.contentRight - geometry.viewportWidth)).toBeLessThanOrEqual(1);
    expect(Math.abs(geometry.navLeft)).toBeLessThanOrEqual(1);
    expect(Math.abs(geometry.navRight - geometry.viewportWidth)).toBeLessThanOrEqual(1);
    expect(Math.abs(geometry.linksLeft - (geometry.viewportWidth - geometry.linksRight)))
      .toBeLessThanOrEqual(2);
    await expectNoHorizontalOverflow(page);
  }

  await page.getByRole("link", { name: "Ещё" }).click();
  await expect(page).toHaveURL(/\/more$/);
  await expect.poll(() => page.locator(".app-shell__content").evaluate((content) => content.scrollTop))
    .toBe(0);
});

test("touch filters retain usable targets and fit a short viewport", async ({ page }, testInfo) => {
  test.skip(
    !["android-like", "iphone-webkit"].includes(testInfo.project.name),
    "Touch-screen acceptance",
  );
  await prepareApp(page);
  await page.setViewportSize({ width: 360, height: 420 });
  await page.goto("/catalog/transceiver_ethernet");

  const filters = page.getByRole("button", { name: "Фильтры", exact: true });
  await expect(filters).toBeVisible();
  expect(await filters.evaluate((element) => element.getBoundingClientRect().height))
    .toBeGreaterThanOrEqual(44);
  await filters.click();

  const dialog = page.getByRole("dialog", { name: "Фильтры" });
  await expect(dialog).toBeVisible();
  const options = dialog.locator(".filter-option");
  await expect(options.first()).toBeVisible();
  expect(await options.first().evaluate((element) => element.getBoundingClientRect().height))
    .toBeGreaterThanOrEqual(48);

  const fitsViewport = await dialog.evaluate((element) => {
    const dialogRect = element.getBoundingClientRect();
    const footerRect = element.querySelector(".sheet__footer")?.getBoundingClientRect();
    return footerRect !== undefined
      && dialogRect.top >= -1
      && dialogRect.bottom <= window.innerHeight + 1
      && footerRect.top >= 0
      && footerRect.bottom <= window.innerHeight + 1;
  });
  expect(fitsViewport).toBe(true);
  await expectNoHorizontalOverflow(page);
});
