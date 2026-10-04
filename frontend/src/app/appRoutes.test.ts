import {
  describe,
  expect,
  it,
} from "vitest";

import {
  APP_DEFAULT_PATH,
  APP_ROUTES,
  isNavigationItemActive,
  isNavigationItemVisible,
  PRIMARY_NAVIGATION,
  routeForPath,
} from "./appRoutes";

describe("application route registry", () => {
  it("keeps route ids and paths unique", () => {
    const ids = APP_ROUTES.map(
      (route) => route.id,
    );
    const paths = APP_ROUTES.map(
      (route) => route.path,
    );

    expect(new Set(ids).size).toBe(
      ids.length,
    );
    expect(new Set(paths).size).toBe(
      paths.length,
    );
  });

  it.each([
    ["/", "catalog"],
    ["/catalog", "catalog"],
    ["/catalog/new", "catalog-new"],
    [
      "/catalog/items/item-1/edit",
      "catalog-edit",
    ],
    [
      "/catalog/items/item-1",
      "catalog-item",
    ],
    [
      "/catalog/transceiver_ethernet",
      "catalog-category",
    ],
    ["/movements", "movements"],
    ["/procurement", "procurement"],
    [
      "/procurement/new",
      "procurement-new",
    ],
    [
      "/procurement/request-1",
      "procurement-detail",
    ],
    ["/more", "more"],
    ["/more/locations", "locations"],
    ["/more/users", "admin-users"],
  ])(
    "resolves %s to %s",
    (pathname, expectedId) => {
      expect(
        routeForPath(pathname)?.id,
      ).toBe(expectedId);
    },
  );

  it("does not resolve unknown paths", () => {
    expect(
      routeForPath("/unknown"),
    ).toBeUndefined();
  });

  it("derives primary navigation from route metadata", () => {
    expect(
      PRIMARY_NAVIGATION.map(
        (item) => [
          item.routeId,
          item.to,
        ],
      ),
    ).toEqual([
      ["catalog", "/catalog"],
      ["movements", "/movements"],
      ["procurement", "/procurement"],
      ["more", "/more"],
    ]);

    expect(APP_DEFAULT_PATH).toBe(
      "/catalog",
    );
  });

  it("uses capability metadata only for navigation visibility", () => {
    const movementItem =
      PRIMARY_NAVIGATION.find(
        (item) =>
          item.routeId === "movements",
      );
    const procurementItem =
      PRIMARY_NAVIGATION.find(
        (item) =>
          item.routeId === "procurement",
      );

    expect(movementItem).toBeDefined();
    expect(procurementItem).toBeDefined();

    expect(
      isNavigationItemVisible(
        movementItem!,
        {
          capabilities: [
            "movement.read_own",
          ],
        },
      ),
    ).toBe(true);

    expect(
      isNavigationItemVisible(
        movementItem!,
        {
          capabilities: [
            "catalog.read",
          ],
        },
      ),
    ).toBe(false);

    expect(
      isNavigationItemVisible(
        procurementItem!,
        {
          capabilities: [
            "procurement.read",
          ],
        },
      ),
    ).toBe(true);
  });

  it("marks nested routes active under their primary destination", () => {
    const catalog =
      PRIMARY_NAVIGATION.find(
        (item) =>
          item.routeId === "catalog",
      )!;

    expect(
      isNavigationItemActive(
        "/catalog/items/item-1",
        catalog,
      ),
    ).toBe(true);

    expect(
      isNavigationItemActive(
        "/procurement",
        catalog,
      ),
    ).toBe(false);
  });
});
