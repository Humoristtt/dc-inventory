import {
  expect,
  type Page,
  type Route,
  test,
} from "@playwright/test";

type Role = "USER" | "ADMIN";

type MockOptions = {
  categoriesFailures?: number;
  emptyCategoriesAfterRetry?: boolean;
  role: Role;
};

type CatalogItemFixture = {
  id: string;
  category: { id: string; key: string; display_name: string };
  manufacturer: { id: string; name: string } | null;
  name: string;
  model: string | null;
  manufacturer_part_number: string | null;
  internal_code: string | null;
  description: string | null;
  accounting_mode: "QUANTITY" | "SERIAL";
  status: "ACTIVE" | "ARCHIVED";
  comment: string | null;
  datasheet_url: string | null;
  technical_data_source: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  attributes: Record<string, string | number | boolean>;
};

const userId = "00000000-0000-4000-8000-000000000111";
const now = "2026-09-03T18:00:00Z";
const category = {
  id: "10000000-0000-4000-8000-000000000001",
  key: "sfp",
  display_name: "SFP-модули",
  description: "Оптические трансиверы",
  default_accounting_mode: "QUANTITY",
  sort_order: 10,
  is_system: true,
};
const categoryDetail = {
  ...category,
  attributes: [
    {
      id: "speed-profile",
      key: "speed_profile",
      label: "Профиль скорости",
      data_type: "TEXT",
      unit: null,
      required: false,
      filterable: false,
      searchable: true,
      card_visible: false,
      detail_visible: true,
      table_visible: true,
      excel_visible: true,
      sort_order: 15,
      filter_type: "NONE",
      allowed_values: null,
      validation_metadata: { max_length: 255, preserve_whitespace: true },
      is_system: true,
    },
    {
      id: "speed",
      key: "speed_mbps",
      label: "Скорость",
      data_type: "INTEGER",
      unit: "Mbps",
      required: true,
      filterable: true,
      searchable: true,
      card_visible: true,
      detail_visible: true,
      table_visible: true,
      excel_visible: true,
      sort_order: 20,
      filter_type: "RANGE",
      allowed_values: null,
      validation_metadata: { min: 1 },
      is_system: true,
    },
    {
      id: "reach-profile",
      key: "reach_profile",
      label: "Профиль дальности",
      data_type: "TEXT",
      unit: null,
      required: false,
      filterable: false,
      searchable: true,
      card_visible: false,
      detail_visible: true,
      table_visible: true,
      excel_visible: true,
      sort_order: 45,
      filter_type: "NONE",
      allowed_values: null,
      validation_metadata: { max_length: 2000, preserve_whitespace: true },
      is_system: true,
    },
    {
      id: "connector",
      key: "connector",
      label: "Разъём",
      data_type: "ENUM",
      unit: null,
      required: false,
      filterable: true,
      searchable: true,
      card_visible: true,
      detail_visible: true,
      table_visible: true,
      excel_visible: true,
      sort_order: 60,
      filter_type: "EXACT",
      allowed_values: ["LC Duplex", "MPO", "MPO/PC"],
      validation_metadata: null,
      is_system: true,
    },
  ],
};

function fixtureItem(): CatalogItemFixture {
  return {
    id: "item-sfp",
    category: { id: category.id, key: category.key, display_name: category.display_name },
    manufacturer: { id: "manufacturer-avago", name: "Avago" },
    name: "Трансивер FC",
    model: "AFBR-57F5MZ-ELX",
    manufacturer_part_number: null,
    internal_code: null,
    description: "Многоскоростной FC трансивер",
    accounting_mode: "QUANTITY",
    status: "ACTIVE",
    comment: null,
    datasheet_url: null,
    technical_data_source: "Синтетическая E2E fixture",
    archived_at: null,
    created_at: now,
    updated_at: now,
    attributes: {
      speed_profile: "4/8/16G FC",
      speed_mbps: 16000,
      reach_profile: "OM3: до 100 м\nOM4: до 125 м",
      connector: "LC Duplex",
    },
  };
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ json: body, status });
}

async function installTelegramMock(page: Page) {
  await page.route("**/vendor/telegram/telegram-web-app.js", (route) =>
    route.fulfill({ body: "", contentType: "application/javascript" }),
  );
  await page.addInitScript(() => {
    const state: {
      callback: (() => void) | null;
      expanded: boolean;
      ready: boolean;
      visible: boolean;
    } = { callback: null, expanded: false, ready: false, visible: false };
    Object.defineProperty(window, "__stage8Telegram", { value: state });
    Object.defineProperty(window, "Telegram", {
      configurable: true,
      value: {
        WebApp: {
          initData: "synthetic-signed-data",
          ready: () => { state.ready = true; },
          expand: () => { state.expanded = true; },
          BackButton: {
            show: () => { state.visible = true; },
            hide: () => { state.visible = false; },
            onClick: (callback: () => void) => { state.callback = callback; },
            offClick: (callback: () => void) => {
              if (state.callback === callback) state.callback = null;
            },
          },
        },
      },
    });
  });
}

async function assertNoHorizontalOverflow(page: Page) {
  await expect.poll(() => page.evaluate(() => (
    document.documentElement.scrollWidth <= window.innerWidth
    && document.body.scrollWidth <= window.innerWidth
  ))).toBe(true);
}

async function assertBottomNavigationClearance(page: Page) {
  const hasClearance = await page.evaluate(() => {
    const content = document.querySelector<HTMLElement>(".app-shell__content");
    const navigation = document.querySelector<HTMLElement>(".bottom-nav__inner");
    if (content === null || navigation === null) return false;
    return Number.parseFloat(getComputedStyle(content).paddingBottom)
      >= navigation.getBoundingClientRect().height;
  });
  expect(hasClearance).toBe(true);
}

async function installApiMock(page: Page, options: MockOptions) {
  let categoriesFailures = options.categoriesFailures ?? 0;
  let item = fixtureItem();
  const manufacturers = [{
    id: "manufacturer-avago",
    name: "Avago",
    created_at: now,
    updated_at: now,
  }];
  const requestedUrls: string[] = [];
  let lastCreatePayload: Record<string, unknown> | null = null;

  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    requestedUrls.push(`${url.pathname}${url.search}`);

    if (url.pathname === "/api/auth/me") {
      return json(route, {
        user: {
          id: userId,
          telegram_user_id: 1001,
          username: "telegram-alias",
          first_name: "Иван",
          last_name: null,
          role: options.role,
          access_status: "APPROVED",
        },
        support: { username: "support", url: "https://t.me/support" },
      });
    }
    if (url.pathname === "/api/catalog/categories") {
      if (categoriesFailures > 0) {
        categoriesFailures -= 1;
        return json(route, { detail: "synthetic failure" }, 500);
      }
      return json(route, options.emptyCategoriesAfterRetry ? [] : [category]);
    }
    if (url.pathname === "/api/catalog/categories/sfp") {
      return json(route, categoryDetail);
    }
    if (url.pathname === "/api/catalog/manufacturers") {
      return json(route, { items: manufacturers, total: manufacturers.length, limit: 200, offset: 0 });
    }
    if (url.pathname === "/api/catalog/items/facets") {
      return json(route, {
        facets: [
          {
            key: "availability",
            label: "Наличие",
            data_type: "ENUM",
            unit: null,
            filter_type: "EXACT",
            values: [{ value: "IN_STOCK", count: 1, label: "В наличии", code: null, name: null }],
            min: null,
            max: null,
          },
          {
            key: "connector",
            label: "Разъём",
            data_type: "ENUM",
            unit: null,
            filter_type: "EXACT",
            values: [{ value: "LC Duplex", count: 1, label: null, code: null, name: null }],
            min: null,
            max: null,
          },
        ],
      });
    }
    if (url.pathname === "/api/catalog/items") {
      const visible = url.searchParams.get("status") === "ARCHIVED"
        ? item.status === "ARCHIVED"
        : item.status === "ACTIVE";
      return json(route, {
        items: visible ? [{
          ...item,
          inventory: { available_count: 8, custody_count: 2, total_count: 10 },
        }] : [],
        total: visible ? 1 : 0,
        limit: 20,
        offset: 0,
      });
    }
    if (url.pathname.startsWith("/api/catalog/items/")) {
      return json(route, item);
    }
    if (url.pathname === "/api/inventory/stock") {
      if (url.searchParams.get("holder_user_id") === userId) {
        return json(route, {
          items: [{
            id: "holder-balance",
            item_id: "quantity-holding",
            item_name: "Патч-корд LC",
            quantity: 4,
            location: null,
            holder: { user_id: userId, display_name: "Иван" },
            updated_at: now,
          }],
          total: 1,
          limit: 200,
          offset: 0,
        });
      }
      return json(route, {
        items: [
          {
            id: "location-balance",
            item_id: item.id,
            item_name: item.name,
            quantity: 8,
            location: { location_id: "location-1", code: "A-01", name: "Основная стойка" },
            holder: null,
            updated_at: now,
          },
          {
            id: "custody-balance",
            item_id: item.id,
            item_name: item.name,
            quantity: 2,
            location: null,
            holder: { user_id: "holder-2", display_name: "Пётр" },
            updated_at: now,
          },
        ],
        total: 2,
        limit: 200,
        offset: 0,
      });
    }
    if (url.pathname === "/api/inventory/units") {
      return json(route, {
        items: url.searchParams.get("holder_user_id") === userId ? [{
          id: "unit-1",
          item_id: "serial-holding",
          item_name: "Сетевая карта",
          serial_number: "SN-100",
          wwn: "10:00:00:00:00:01",
          comment: null,
          state: "ISSUED",
          location: null,
          holder: { user_id: userId, display_name: "Иван" },
          created_at: now,
          updated_at: now,
        }] : [],
        total: url.searchParams.get("holder_user_id") === userId ? 1 : 0,
        limit: 200,
        offset: 0,
      });
    }
    if (url.pathname === "/api/admin/catalog/manufacturers") {
      const manufacturer = {
        id: "manufacturer-new",
        name: String((request.postDataJSON() as { name: string }).name).trim(),
        created_at: now,
        updated_at: now,
      };
      manufacturers.push(manufacturer);
      return json(route, manufacturer, 201);
    }
    if (url.pathname === "/api/admin/catalog/items/check-duplicates") {
      return json(route, {
        candidates: [{
          item_id: "duplicate-item",
          name: "Похожая позиция",
          model: "DSO-25",
          manufacturer_id: "manufacturer-new",
          manufacturer_name: "D-WDM.RU",
          manufacturer_part_number: null,
          reason: "same_category_manufacturer_name_model",
        }],
      });
    }
    if (url.pathname === "/api/admin/catalog/items" && request.method() === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      lastCreatePayload = payload;
      item = {
        ...fixtureItem(),
        id: "item-created",
        manufacturer: { id: "manufacturer-new", name: "D-WDM.RU" },
        name: String(payload.name),
        model: payload.model === null ? null : String(payload.model),
        attributes: payload.attributes as Record<string, string | number | boolean>,
      };
      return json(route, item, 201);
    }
    if (/^\/api\/admin\/catalog\/items\/[^/]+$/.test(url.pathname) && request.method() === "PATCH") {
      const patch = request.postDataJSON() as Partial<CatalogItemFixture>;
      item = { ...item, ...patch, updated_at: "2026-09-03T18:01:00Z" };
      return json(route, item);
    }
    if (url.pathname.endsWith("/archive")) {
      item = { ...item, status: "ARCHIVED", archived_at: "2026-09-03T18:02:00Z" };
      return json(route, item);
    }
    if (url.pathname.endsWith("/unarchive")) {
      item = { ...item, status: "ACTIVE", archived_at: null };
      return json(route, item);
    }
    return json(route, { detail: `Unhandled synthetic route: ${url.pathname}` }, 500);
  });

  return {
    get lastCreatePayload() { return lastCreatePayload; },
    requestedUrls,
  };
}

test("approved USER navigates catalog with preserved filters and projection detail", async ({ page }) => {
  await installTelegramMock(page);
  await installApiMock(page, { role: "USER" });
  await page.goto("/catalog");

  await expect(page.getByRole("heading", { name: "Найти оборудование" })).toBeVisible();
  await expect(page.getByRole("link", { name: "+ Новая позиция" })).toHaveCount(0);
  await page.getByRole("link", { name: /SFP-модули/ }).click();
  await page.getByRole("button", { name: "Фильтры" }).click();
  await page.getByLabel("В наличии").check();
  await page.getByRole("button", { name: "Применить" }).click();
  await expect(page).toHaveURL(/availability=IN_STOCK/);

  await page.getByRole("heading", { name: "AFBR-57F5MZ-ELX" }).click();
  await expect(page.getByRole("heading", { name: "Наличие и хранение" })).toBeVisible();
  await expect(page.getByText("A-01")).toBeVisible();
  await expect(page.getByText("Пётр")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Управление позицией" })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => (
    (window as unknown as { __stage8Telegram: { visible: boolean } }).__stage8Telegram.visible
  ))).toBe(true);

  await page.evaluate(() => {
    (window as unknown as { __stage8Telegram: { callback: (() => void) | null } })
      .__stage8Telegram.callback?.();
  });
  await expect(page).toHaveURL(/\/catalog\/sfp\?.*availability=IN_STOCK/);
  await assertBottomNavigationClearance(page);
  await assertNoHorizontalOverflow(page);
});

test("ADMIN completes create, edit, archive and unarchive lifecycle", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-admin", "desktop ADMIN acceptance");
  await installTelegramMock(page);
  const api = await installApiMock(page, { role: "ADMIN" });
  await page.goto("/catalog");

  await page.getByRole("link", { name: "+ Новая позиция" }).click();
  await page.getByLabel(/^Название/).fill("Трансивер 10/25G");
  await page.getByLabel("Модель").fill("DSO-25");
  await page.getByLabel(/^Профиль скорости/).fill("10/25 Гбит/с");
  await page.getByLabel(/^Скорость/).fill("25000");
  await page.getByLabel(/^Профиль дальности/).fill("OM3: 30 м без RS-FEC\nOM4: 100 м с RS-FEC");
  await page.getByLabel("Разъём").selectOption("MPO/PC");

  await page.getByRole("button", { name: "+ Новый" }).click();
  await page.getByLabel("Название нового производителя").fill("D-WDM.RU");
  await page.getByRole("button", { name: "Создать", exact: true }).click();
  await expect(page.getByLabel("Название *")).toHaveValue("Трансивер 10/25G");
  await expect(page.getByLabel("Производитель")).toHaveValue("manufacturer-new");

  await page.getByRole("button", { name: "Проверить и создать" }).click();
  await expect(page.getByRole("heading", { name: "Похожие позиции уже есть" })).toBeVisible();
  await page.getByRole("button", { name: "Всё равно создать" }).click();
  await expect(page).toHaveURL(/\/catalog\/items\/item-created$/);
  expect(api.lastCreatePayload).toMatchObject({
    manufacturer_part_number: null,
    accounting_mode: "QUANTITY",
    attributes: {
      speed_profile: "10/25 Гбит/с",
      speed_mbps: 25000,
      connector: "MPO/PC",
    },
  });

  await page.getByRole("link", { name: "Редактировать" }).click();
  await page.getByLabel("Комментарий").fill("Проверено в E2E");
  await page.getByRole("button", { name: "Сохранить" }).click();
  await expect(page.getByText("Проверено в E2E")).toBeVisible();

  await page.getByRole("button", { name: "В архив" }).click();
  await expect(page.getByText(/Текущий складской остаток.*не удаляются/)).toBeVisible();
  await page.getByRole("button", { name: "Подтвердить" }).click();
  await expect(page.getByRole("button", { name: "Вернуть из архива" })).toBeVisible();
  await page.getByRole("button", { name: "Вернуть из архива" }).click();
  await page.getByRole("button", { name: "Подтвердить" }).click();
  await expect(page.getByRole("button", { name: "В архив" })).toBeVisible();
  await assertNoHorizontalOverflow(page);
});

test("ADMIN metadata form remains usable in Telegram Desktop narrow", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "telegram-desktop-narrow", "narrow form acceptance");
  await installTelegramMock(page);
  await installApiMock(page, { role: "ADMIN" });
  await page.goto("/catalog/new?category=sfp");

  await expect(page.getByRole("heading", { name: "Создать позицию" })).toBeVisible();
  await expect(page.getByLabel(/^Профиль дальности/)).toBeVisible();
  await page.getByRole("button", { name: "+ Новый" }).click();
  await expect(page.getByLabel("Название нового производителя")).toBeVisible();
  await page.getByRole("button", { name: "Проверить и создать" }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "Проверить и создать" })).toBeVisible();
  await assertBottomNavigationClearance(page);
  await assertNoHorizontalOverflow(page);
});

test("My Equipment shows quantity and serial holdings using internal UUID", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "iphone-like", "iPhone-like holdings acceptance");
  await installTelegramMock(page);
  const api = await installApiMock(page, { role: "USER" });
  await page.goto("/mine");

  await expect(page.getByRole("heading", { name: "Патч-корд LC" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Сетевая карта" })).toBeVisible();
  await expect(page.getByText("SN SN-100")).toBeVisible();
  expect(api.requestedUrls.some((url) => url.includes(`holder_user_id=${userId}`))).toBe(true);
  expect(api.requestedUrls.every((url) => !url.includes("telegram-alias"))).toBe(true);
  await expect(page.getByRole("link", { name: /Моё/ })).toHaveAttribute("aria-current", "page");
  await assertBottomNavigationClearance(page);
  await assertNoHorizontalOverflow(page);
});

test("catalog API error retries into a compact empty state", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "android-like", "Android-like recovery acceptance");
  await installTelegramMock(page);
  await installApiMock(page, {
    role: "USER",
    // React StrictMode aborts the first development fetch before the query retry.
    categoriesFailures: 3,
    emptyCategoriesAfterRetry: true,
  });
  await page.goto("/catalog");

  await expect(page.getByText("Не удалось загрузить категории")).toBeVisible();
  await page.getByRole("button", { name: "Повторить" }).click();
  await expect(page.getByText("Категорий пока нет")).toBeVisible();
  await assertNoHorizontalOverflow(page);
});
