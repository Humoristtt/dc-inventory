import { expect, type Page, type Route, test } from "@playwright/test";

const userId = "00000000-0000-4000-8000-000000000111";
const now = "2026-09-07T12:00:00Z";
const family = {id:"family",key:"transceivers",display_name:"Трансиверы",description:"Оптические трансиверы",parent_id:null,sort_order:0,is_system:true};
const category = {id:"leaf",key:"transceiver_ethernet",display_name:"Ethernet",description:null,parent_id:family.id,sort_order:0,is_system:true};
const attributes = {speed:"10 Гбит/с",wavelength:"1310 нм",reach:"до 10 км",form_factor:"SFP+",fiber:"SMF",connector:"LC"};
const labels: Record<string,string> = {speed:"Скорость",wavelength:"Длина волны",reach:"Дальность",form_factor:"Форм-фактор",fiber:"Волокно / среда",connector:"Разъём"};
const categoryDetail = {...category,attributes:Object.keys(attributes).map((key,index)=>({id:key,key,label:labels[key],data_type:"TEXT",unit:null,required:true,filterable:true,searchable:true,card_visible:true,detail_visible:true,table_visible:true,excel_visible:true,sort_order:index,filter_type:"EXACT",allowed_values:null,validation_metadata:{max_length:2000},is_system:true}))};
const location = {id:"location-1",code:"A-01",name:"Тестовый склад",location_type:"WAREHOUSE",address:null,status:"ACTIVE",archived_at:null,created_at:now,updated_at:now};
function fixtureItem() {return {id:"item-1",category:{id:category.id,key:category.key,display_name:category.display_name},manufacturer:{id:"maker",name:"Synthetic"},name:"Тестовый трансивер",model:"TEST-10G",status:"ACTIVE",archived_at:null,created_at:now,updated_at:now,attributes:{...attributes,reach_m:10000}};}
function json(route:Route, body:unknown, status=200) {return route.fulfill({json:body,status});}
async function installTelegramMock(
  page: Page,
  platform = "unknown",
) {
  await page.route("**/vendor/telegram/telegram-web-app.js", (route) =>
    route.fulfill({ body: "", contentType: "application/javascript" }),
  );
  await page.addInitScript((telegramPlatform: string) => {
    const state: {
      callback: (() => void) | null;
      expanded: boolean;
      fullscreen: boolean;
      fullscreenRequested: boolean;
      ready: boolean;
      visible: boolean;
    } = {
      callback: null,
      expanded: false,
      fullscreen: false,
      fullscreenRequested: false,
      ready: false,
      visible: false,
    };

    const webAppEvents =
      new Map<string, Set<() => void>>();

    const emitWebAppEvent = (name: string) => {
      for (
        const handler
        of webAppEvents.get(name) ?? []
      ) {
        handler();
      }
    };
    Object.defineProperty(window, "__stage8Telegram", { value: state });
    Object.defineProperty(window, "Telegram", {
      configurable: true,
      value: {
        WebApp: {
          initData: "synthetic-signed-data",
          platform: telegramPlatform,
          ready: () => { state.ready = true; },
          expand: () => { state.expanded = true; },
          get isFullscreen() {
            return state.fullscreen;
          },
          requestFullscreen: () => {
            state.fullscreenRequested = true;
            state.fullscreen = true;
            emitWebAppEvent("fullscreenChanged");
          },
          exitFullscreen: () => {
            state.fullscreenRequested = false;
            state.fullscreen = false;
            emitWebAppEvent("fullscreenChanged");
          },
          onEvent: (
            name: string,
            handler: () => void,
          ) => {
            const handlers =
              webAppEvents.get(name) ?? new Set();
            handlers.add(handler);
            webAppEvents.set(name, handlers);
          },
          offEvent: (
            name: string,
            handler: () => void,
          ) => {
            webAppEvents.get(name)?.delete(handler);
          },
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
  }, platform);
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

async function installApiMock(page:Page, role:"USER"|"ADMIN", failures=0) {
  let item=fixtureItem(); let quantity=10;
  const requests:string[]=[]; const mutations:Record<string,unknown>[]=[];
  const makers=[{id:"maker",name:"Synthetic",created_at:now,updated_at:now}];
  const movements:Record<string,unknown>[]=[];
  await page.route(/^https?:\/\/[^/]+\/api\//, async route=>{
    const request=route.request(); const url=new URL(request.url()); const path=url.pathname;
    requests.push(path+url.search);
    if(path === "/api/auth/me") return json(route,{user:{id:userId,telegram_user_id:1001,first_name:"Иван",last_name:null,username:"synthetic",role,access_status:"APPROVED"},support:{username:"support",url:"https://t.me/support"}});
    if(path === "/api/catalog/categories") {
      if(failures-- > 0) return json(route,{detail:"synthetic failure"},500);
      return json(route,[family,category]);
    }
    if(path.startsWith("/api/catalog/categories/")) return json(route,path.endsWith(family.key) ? {...family,attributes:[]} : categoryDetail);
    if(path === "/api/catalog/manufacturers") return json(route,{items:makers,total:makers.length,limit:100,offset:0});
    if(path === "/api/catalog/items/facets") {
      const facet = url.searchParams.get("facet");

      if (facet !== null && facet in attributes) {
        const value =
          attributes[facet as keyof typeof attributes];

        return json(route,{
          facets:[{
            key:facet,
            label:labels[facet],
            data_type:"TEXT",
            unit:null,
            filter_type:"EXACT",
            values:[{
              value,
              label:value,
              count:1,
            }],
            values_has_more:false,
            min:null,
            max:null,
          }],
        });
      }

      return json(route,{facets:[{key:"availability",label:"Наличие",data_type:"ENUM",unit:null,filter_type:"EXACT",values:[{value:"IN_STOCK",label:"В наличии",count:1},{value:"OUT_OF_STOCK",label:"Нет в наличии",count:1}],min:null,max:null}]});
    }
    if(path === "/api/catalog/items") return json(route,{items:[{...item,inventory:{available_count:quantity,total_count:quantity}}],total:1,limit:20,offset:0});
    if(path.startsWith("/api/catalog/items/")) return json(route,item);
    if(path === `/api/inventory/items/${item.id}/summary`) return json(route,{total_count:quantity,locations:[{id:"balance",item_id:item.id,item_name:item.name,quantity,location:{location_id:location.id,code:location.code,name:location.name},updated_at:now}]});
    if(path === "/api/inventory/locations") return json(route,{items:[location],total:1,limit:200,offset:0});
    if(path === "/api/inventory/movement-actors") return json(route,[{id:userId,name:"Иван"}]);
    if(path === "/api/inventory/movements/feed") {
      return json(route,{
        items:[...movements].reverse(),
        limit:30,
        next_before_journal_seq:null,
      });
    }
    if(path === "/api/inventory/movements") {
      if(request.method() === "POST") {
        const payload=request.postDataJSON() as Record<string,unknown>; mutations.push(payload);
        const line=(payload.lines as {quantity:number}[])[0];
        quantity += payload.movement_type === "ISSUE" ? -line.quantity : line.quantity;
        const movement={...payload,id:`movement-${movements.length}`,journal_seq:movements.length+1,occurred_at:now,actor_user_id:userId,actor_display_name_snapshot:"Иван",source_location_name_snapshot:payload.source_location_id ? location.name : null,destination_location_name_snapshot:payload.destination_location_id ? location.name : null,lines:[{id:"line",item_id:item.id,item_name_snapshot:item.name,quantity:line.quantity}]};
        movements.push(movement); return json(route,movement,201);
      }
      return json(route,{items:movements,total:movements.length,limit:30,offset:0});
    }
    if(path === "/api/admin/catalog/manufacturers") {
      const maker={id:"new-maker",name:String(request.postDataJSON().name),created_at:now,updated_at:now};makers.push(maker);return json(route,maker,201);
    }
    if(path === "/api/admin/catalog/items" || request.method() === "PATCH") {
      const payload=request.postDataJSON() as Record<string, unknown>;mutations.push(payload);
      item={...item,...payload,manufacturer:makers.at(-1)!,category:item.category};return json(route,item,path.endsWith("items") ? 201 : 200);
    }
    if(path.endsWith("/archive") || path.endsWith("/unarchive")) {item={...item,status:path.endsWith("/unarchive")?"ACTIVE":"ARCHIVED"};return json(route,item);}
    return json(route,{detail:`Unhandled route ${path}`},500);
  });
  return {requests,mutations};
}


test(
  "category opens on first physical activation after scroll",
  async ({ page }, testInfo) => {
    await installTelegramMock(page);
    await installApiMock(page, "USER");

    const touchProject =
      testInfo.project.name === "android-like"
      || testInfo.project.name === "iphone-webkit";

    await page.setViewportSize(
      touchProject
        ? { width: 360, height: 420 }
        : { width: 1280, height: 500 },
    );

    await page.goto("/catalog");

    const categoryLink = page.getByRole(
      "link",
      { name: /Трансиверы/ },
    );

    await expect(categoryLink).toBeVisible();
    await categoryLink.scrollIntoViewIfNeeded();

    await expect.poll(
      () => page.evaluate(() => window.scrollY),
    ).toBeGreaterThan(0);

    const box = await categoryLink.boundingBox();
    expect(box).not.toBeNull();

    if (box === null) {
      throw new Error("Category link has no bounding box");
    }

    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;

    if (touchProject) {
      await page.touchscreen.tap(x, y);
    } else {
      await page.mouse.click(x, y);
    }

    await expect(page).toHaveURL(
      /\/catalog\/transceivers$/,
    );

    await expect.poll(
      () => page.evaluate(() => window.scrollY),
    ).toBe(0);
  },
);

test("USER browses hierarchy, retains server filters, and uses Telegram back", async ({page})=>{
  await installTelegramMock(page); const api=await installApiMock(page,"USER");
  await page.goto("/catalog/new?category=transceiver_ethernet");
  await expect(page).toHaveURL(/\/catalog$/);
  await page.getByRole("link",{name:/Трансиверы/}).click();
  await page.getByRole("link",{name:"Ethernet",exact:true}).click();
  await page.getByRole("button",{name:"Фильтры"}).click();
  await page.getByLabel("В наличии",{exact:true}).check();
  await page.getByRole("button",{name:"Применить"}).click();
  await expect(page).toHaveURL(/availability=IN_STOCK/);
  await expect.poll(
    () => api.requests.some(
      url => url.includes("category=transceiver_ethernet")
        && url.includes("availability=IN_STOCK"),
    ),
  ).toBe(true);
  await page.getByRole("heading",{name:/TEST-10G/}).click();
  await expect(page.getByText("В наличии: 10")).toBeVisible();
  await expect(page.getByText(location.name,{exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Переместить"})).toHaveCount(0);
  await page.evaluate(()=>{(window as unknown as {__stage8Telegram:{callback:(()=>void)|null}}).__stage8Telegram.callback?.();});
  await expect(page).toHaveURL(/\/catalog\/transceiver_ethernet\?.*availability=IN_STOCK/);
  await assertNoHorizontalOverflow(page);await assertBottomNavigationClearance(page);
});

test("USER issues and returns quantities, then reads movement history",async({page})=>{
  await installTelegramMock(page);const api=await installApiMock(page,"USER");
  await page.goto("/catalog/items/item-1");
  for(const [label,amount,kind] of [["Взять","4","ISSUE"],["Вернуть","16","RETURN"]]) {
    await page.getByRole("button",{name:label,exact:true}).click();
    await page.getByLabel("Количество",{exact:true}).fill(amount);
    await page.getByRole("button",{name:"Подтвердить",exact:true}).click();
    await expect.poll(()=>api.mutations.at(-1)?.movement_type).toBe(kind);
    await expect(page.getByRole("button",{name:"Подтвердить",exact:true})).toHaveCount(0);
  }
  await expect(page.getByText("В наличии: 22")).toBeVisible();
  expect(api.mutations[0]).toMatchObject({movement_type:"ISSUE",source_location_id:location.id,lines:[{item_id:"item-1",quantity:4}]});
  expect(api.mutations[1]).toMatchObject({movement_type:"RETURN",destination_location_id:location.id,lines:[{item_id:"item-1",quantity:16}]});
  await page.locator('.bottom-nav__item[href="/movements"]').click();
  await expect(page.getByLabel("Период")).toHaveValue("3m");
  await expect(page.locator(".movement-entry")).toHaveCount(2);
  await page.getByLabel("Период").selectOption("30d");
  await page.getByLabel("Сотрудник").selectOption(userId);
  await page.getByLabel("Оборудование").selectOption("long-range");
  await page.getByLabel("Место хранения").selectOption(location.id);
  await expect.poll(()=>api.requests.some(url=>url.includes("period=30d") && url.includes("actor_user_id="+userId) && url.includes("long_range=true") && url.includes("location_id="+location.id))).toBe(true);
  await assertNoHorizontalOverflow(page);await assertBottomNavigationClearance(page);
});

test("ADMIN creates metadata-driven equipment, edits and archives",async({page})=>{
  await installTelegramMock(page);const api=await installApiMock(page,"ADMIN");
  await page.goto("/catalog/new");
  await page.getByRole("combobox",{name:"Раздел"}).selectOption("family");
  await page.getByRole("combobox",{name:"Категория"}).selectOption("transceiver_ethernet");
  await page.getByLabel("Название оборудования",{exact:true}).fill("Synthetic new item");
  const manufacturerInput = page.getByRole("combobox",{name:"Производитель"});
  await manufacturerInput.fill("Syn");
  await expect(page.getByRole("option",{name:"Synthetic"})).toBeVisible();
  await page.getByRole("option",{name:"Synthetic"}).click();
  await expect(manufacturerInput).toHaveValue("Synthetic");
  await page.getByLabel("Модель",{exact:true}).fill("NEW-10G");
  for(const [key,value] of Object.entries(attributes)) await page.getByLabel(new RegExp("^"+labels[key])).fill(value);
  await page.getByRole("button",{name:"Сохранить",exact:true}).click();
  await expect(page).toHaveURL(/\/catalog\/items\/item-1$/);
  expect(api.mutations[0]).toMatchObject({category_key:category.key,name:"Synthetic new item",model:"NEW-10G",attributes});
  await page.getByRole("link",{name:"Редактировать"}).click();
  await page.getByLabel("Модель",{exact:true}).fill("EDITED-10G");
  await page.getByRole("button",{name:"Сохранить",exact:true}).click();
  await expect(page.getByRole("heading",{name:"EDITED-10G"})).toBeVisible();
  for(const name of ["В архив","Вернуть из архива"]) {
    await page.getByRole("button",{name,exact:true}).click();
    await page.getByRole("button",{name:"Подтвердить",exact:true}).click();
    await expect(page.getByRole("button",{name: name === "В архив" ? "Вернуть из архива" : "В архив",exact:true})).toBeVisible();
  }
  await assertNoHorizontalOverflow(page);await assertBottomNavigationClearance(page);
});

test("catalog failure supports retry",async({page})=>{
  await installTelegramMock(page);await installApiMock(page,"USER",3);
  await page.goto("/catalog");
  await expect(page.getByText("Не удалось загрузить категории")).toBeVisible();
  await page.getByRole("button",{name:"Повторить"}).click();
  await expect(page.getByRole("link",{name:/Трансиверы/})).toBeVisible();
});
test(
  "desktop UX uses windowed expanded viewport, responsive shell and internal Escape",
  async ({ page }, testInfo) => {
    test.skip(
      ![
        "desktop-admin",
        "desktop-standard",
        "desktop-ultrawide",
      ].includes(
        testInfo.project.name,
      ),
      "desktop UX acceptance",
    );

    await installTelegramMock(page, "tdesktop");
    await installApiMock(page, "ADMIN");

    await page.goto("/catalog");

    await expect(
      page.getByText("Инвентаризация ЦОД", { exact: true }),
    ).toBeVisible();

    const telegramViewportState = await page.evaluate(() => (
      (
        window as unknown as {
          __stage8Telegram: {
            expanded: boolean;
            fullscreenRequested: boolean;
          };
        }
      ).__stage8Telegram
    ));

    expect(telegramViewportState.expanded).toBe(true);
    expect(telegramViewportState.fullscreenRequested).toBe(true);

    const exitFullscreenButton = page.getByRole(
      "button",
      { name: "Выйти из полного экрана" },
    );

    await expect(exitFullscreenButton).toBeVisible();

    const fixedFullscreenAncestor = await exitFullscreenButton.evaluate(
      (button) => {
        let node: HTMLElement | null = button as HTMLElement;

        while (node !== null) {
          if (getComputedStyle(node).position === "fixed") {
            return node.className;
          }
          node = node.parentElement;
        }

        return null;
      },
    );

    expect(fixedFullscreenAncestor).toBeNull();

    await exitFullscreenButton.click();

    await expect.poll(
      () => page.evaluate(() => (
        (
          window as unknown as {
            __stage8Telegram: {
              fullscreenRequested: boolean;
            };
          }
        ).__stage8Telegram.fullscreenRequested
      )),
    ).toBe(false);

    const fullscreenButton = page.getByRole(
      "button",
      { name: "На весь экран" },
    );

    await expect(fullscreenButton).toBeVisible();

    // Manual fullscreen control remains available after leaving
    // the automatically requested desktop fullscreen mode.
    await fullscreenButton.click();

    await expect.poll(
      () => page.evaluate(() => (
        (
          window as unknown as {
            __stage8Telegram: {
              fullscreenRequested: boolean;
            };
          }
        ).__stage8Telegram.fullscreenRequested
      )),
    ).toBe(true);

    await expect(exitFullscreenButton).toBeVisible();
    await exitFullscreenButton.click();

    await expect(
      page.getByRole(
        "button",
        { name: "На весь экран" },
      ),
    ).toBeVisible();

    await expect(
      page.getByRole("link", { name: /\+ Новая/ }),
    ).toHaveCount(0);

    const columns = await page.locator(".category-grid").evaluate(
      (element) =>
        getComputedStyle(element)
          .gridTemplateColumns
          .trim()
          .split(/\s+/)
          .filter(Boolean)
          .length,
    );

    expect(columns).toBe(4);

    if (testInfo.project.name === "desktop-ultrawide") {
      const geometry = await page.evaluate(() => {
        const shell =
          document.querySelector<HTMLElement>(
            ".app-shell__content",
          );

        const catalog =
          document.querySelector<HTMLElement>(
            ".catalog-page",
          );

        if (shell === null || catalog === null) {
          return null;
        }

        const shellRect = shell.getBoundingClientRect();
        const catalogRect = catalog.getBoundingClientRect();

        return {
          viewportWidth: window.innerWidth,
          shellLeft: shellRect.left,
          shellRight: shellRect.right,
          shellWidth: shellRect.width,
          catalogWidth: catalogRect.width,
        };
      });

      expect(geometry).not.toBeNull();

      if (geometry === null) {
        throw new Error("desktop geometry unavailable");
      }

      expect(geometry.shellWidth).toBeLessThanOrEqual(1921);
      expect(geometry.catalogWidth).toBeLessThanOrEqual(1921);

      const leftGutter = geometry.shellLeft;
      const rightGutter =
        geometry.viewportWidth - geometry.shellRight;

      expect(Math.abs(leftGutter - rightGutter))
        .toBeLessThanOrEqual(2);

      expect(leftGutter).toBeGreaterThan(250);
    }

    await page.evaluate(() => {
      window.scrollTo(0, document.documentElement.scrollHeight);
    });

    await page.getByRole(
      "link",
      { name: /Трансиверы/ },
    ).click();

    await page.getByRole(
      "link",
      { name: "Ethernet", exact: true },
    ).click();

    await expect.poll(
      () => page.evaluate(() => window.scrollY),
    ).toBe(0);

    if (
      testInfo.project.name === "desktop-standard"
      || testInfo.project.name === "desktop-ultrawide"
    ) {
      const toolbarFontSize = await page
        .getByRole("button", { name: "Фильтры" })
        .evaluate(
          (element) => Number.parseFloat(
            getComputedStyle(element).fontSize,
          ),
        );

      expect(toolbarFontSize).toBeGreaterThanOrEqual(13);
    }

    await page.getByRole(
      "button",
      { name: "Фильтры" },
    ).click();

    await expect(
      page.getByRole(
        "dialog",
        { name: "Фильтры" },
      ),
    ).toBeVisible();

    await page.keyboard.press("Escape");

    await expect(
      page.getByRole(
        "dialog",
        { name: "Фильтры" },
      ),
    ).toHaveCount(0);

    await expect(page).toHaveURL(/\/catalog\/transceiver_ethernet/);

    await expect(
      page.getByRole(
        "heading",
        { name: /TEST-10G/ },
      ),
    ).toBeVisible();

    await assertBottomNavigationClearance(page);
    await assertNoHorizontalOverflow(page);
  },
);

test(
  "desktop forms keep centered two-column geometry",
  async ({ page }, testInfo) => {
    test.skip(
      ![
        "desktop-admin",
        "desktop-standard",
        "desktop-ultrawide",
      ].includes(testInfo.project.name),
      "desktop form acceptance",
    );

    await installTelegramMock(page, "tdesktop");
    await installApiMock(page, "ADMIN");

    await page.goto("/catalog/new");

    await page
      .getByRole("combobox", { name: "Раздел" })
      .selectOption("family");

    await page
      .getByRole("combobox", { name: "Категория" })
      .selectOption("transceiver_ethernet");

    const speed = page.getByRole(
      "combobox",
      { name: "Скорость" },
    );

    await expect(speed).toBeVisible();

    await speed.fill("10");

    await expect(
      page.getByRole(
        "option",
        { name: "10 Гбит/с" },
      ),
    ).toBeVisible();

    await page.keyboard.press("Escape");

    await expect(
      page.getByRole(
        "option",
        { name: "10 Гбит/с" },
      ),
    ).toHaveCount(0);

    await expect.poll(
      () => page.evaluate(() => (
        (
          window as unknown as {
            __stage8Telegram: {
              fullscreenRequested: boolean;
            };
          }
        ).__stage8Telegram.fullscreenRequested
      )),
    ).toBe(true);

    await speed.fill("10 Г");

    await expect(
      page.getByRole(
        "option",
        { name: "10 Гбит/с" },
      ),
    ).toBeVisible();

    await page.keyboard.press("Escape");

    await expect(
      page.getByRole(
        "option",
        { name: "10 Гбит/с" },
      ),
    ).toHaveCount(0);

    const catalogGeometry = await page.evaluate(() => {
      const body =
        document.querySelector<HTMLElement>(
          ".catalog-page__body",
        );

      const form =
        document.querySelector<HTMLElement>(
          ".catalog-form",
        );

      const panel =
        form?.querySelector<HTMLElement>(
          ".detail-panel",
        );

      const toolbar =
        document.querySelector<HTMLElement>(
          ".detail-header .page-toolbar",
        );

      const title =
        document.querySelector<HTMLElement>(
          ".detail-header__row--title",
        );

      if (
        body === null
        || form === null
        || panel == null
        || toolbar === null
        || title === null
      ) {
        return null;
      }

      const bodyRect = body.getBoundingClientRect();
      const formRect = form.getBoundingClientRect();
      const toolbarRect = toolbar.getBoundingClientRect();
      const titleRect = title.getBoundingClientRect();

      return {
        formWidth: formRect.width,
        leftGap: formRect.left - bodyRect.left,
        rightGap: bodyRect.right - formRect.right,
        gridTemplateColumns:
          getComputedStyle(panel).gridTemplateColumns,
        toolbarBottom: toolbarRect.bottom,
        titleTop: titleRect.top,
      };
    });

    expect(catalogGeometry).not.toBeNull();

    if (catalogGeometry === null) {
      throw new Error(
        "catalog form geometry unavailable",
      );
    }

    expect(catalogGeometry.formWidth)
      .toBeLessThanOrEqual(1181);

    expect(
      Math.abs(
        catalogGeometry.leftGap
        - catalogGeometry.rightGap,
      ),
    ).toBeLessThanOrEqual(2);

    expect(
      catalogGeometry.gridTemplateColumns,
    ).toMatch(/^repeat\(2,/);

    expect(catalogGeometry.toolbarBottom)
      .toBeLessThanOrEqual(
        catalogGeometry.titleTop + 0.5,
      );

    const speedHeight = await speed.evaluate(
      (element) =>
        element.getBoundingClientRect().height,
    );

    expect(speedHeight).toBeGreaterThanOrEqual(58);
    expect(speedHeight).toBeLessThanOrEqual(66);

    await expect(
      page.locator(".catalog-form textarea"),
    ).toHaveCount(0);

    await assertNoHorizontalOverflow(page);

    await page.goto("/more/locations");

    await page
      .getByRole(
        "button",
        { name: "Добавить место хранения" },
      )
      .click();

    await expect(
      page.getByRole(
        "heading",
        { name: "Новое место хранения" },
      ),
    ).toBeVisible();

    const locationGeometry = await page.evaluate(() => {
      const body =
        document.querySelector<HTMLElement>(
          ".catalog-page__body",
        );

      const form =
        document.querySelector<HTMLElement>(
          ".warehouse-form",
        );

      const fieldset =
        form?.querySelector<HTMLElement>(
          "fieldset",
        );

      if (
        body === null
        || form === null
        || fieldset == null
      ) {
        return null;
      }

      const bodyRect = body.getBoundingClientRect();
      const formRect = form.getBoundingClientRect();

      return {
        formWidth: formRect.width,
        leftGap: formRect.left - bodyRect.left,
        rightGap: bodyRect.right - formRect.right,
        gridTemplateColumns:
          getComputedStyle(fieldset).gridTemplateColumns,
      };
    });

    expect(locationGeometry).not.toBeNull();

    if (locationGeometry === null) {
      throw new Error(
        "location form geometry unavailable",
      );
    }

    expect(locationGeometry.formWidth)
      .toBeLessThanOrEqual(1181);

    expect(
      Math.abs(
        locationGeometry.leftGap
        - locationGeometry.rightGap,
      ),
    ).toBeLessThanOrEqual(2);

    expect(
      locationGeometry.gridTemplateColumns,
    ).toMatch(/^repeat\(2,/);

    await assertNoHorizontalOverflow(page);
  },
);
