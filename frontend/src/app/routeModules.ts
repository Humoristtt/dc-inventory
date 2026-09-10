export const loadCatalogLandingPage = () =>
  import("../pages/catalog/CatalogLandingPage").then(
    (module) => ({ default: module.CatalogLandingPage }),
  );

export const loadCategoryPage = () =>
  import("../pages/catalog/CategoryPage").then(
    (module) => ({ default: module.CategoryPage }),
  );

export const loadItemDetailPage = () =>
  import("../pages/catalog/ItemDetailPage").then(
    (module) => ({ default: module.ItemDetailPage }),
  );

export const loadItemFormPage = () =>
  import("../pages/catalog/ItemFormPage").then(
    (module) => ({ default: module.ItemFormPage }),
  );

export const loadMovementsPage = () =>
  import("../pages/inventory/MovementsPage").then(
    (module) => ({ default: module.MovementsPage }),
  );

export const loadLocationsPage = () =>
  import("../pages/inventory/LocationsPage").then(
    (module) => ({ default: module.LocationsPage }),
  );

export const loadMorePage = () =>
  import("../pages/more/MorePage").then(
    (module) => ({ default: module.MorePage }),
  );

export const loadAdminUsersPage = () =>
  import("../pages/admin/AdminUsersPage").then(
    (module) => ({ default: module.AdminUsersPage }),
  );

type RouteLoader = () => Promise<unknown>;

function routeLoaderForPath(pathname: string): RouteLoader | undefined {
  if (pathname === "/catalog" || pathname === "/") {
    return loadCatalogLandingPage;
  }

  if (
    pathname === "/catalog/new"
    || /^\/catalog\/items\/[^/]+\/edit$/.test(pathname)
  ) {
    return loadItemFormPage;
  }

  if (/^\/catalog\/items\/[^/]+$/.test(pathname)) {
    return loadItemDetailPage;
  }

  if (pathname.startsWith("/catalog/")) {
    return loadCategoryPage;
  }

  if (pathname === "/movements") {
    return loadMovementsPage;
  }

  if (pathname === "/more/locations") {
    return loadLocationsPage;
  }

  if (pathname === "/more/users") {
    return loadAdminUsersPage;
  }

  if (pathname === "/more") {
    return loadMorePage;
  }

  return undefined;
}

export async function preloadRouteForPath(pathname: string): Promise<void> {
  const loader = routeLoaderForPath(pathname);

  if (loader === undefined) {
    return;
  }

  try {
    await loader();
  } catch {
    // RouteContent remains the recovery boundary for a real chunk failure.
  }
}

export async function preloadApplicationRoutes(): Promise<void> {
  await Promise.allSettled([
    loadCatalogLandingPage(),
    loadCategoryPage(),
    loadItemDetailPage(),
    loadItemFormPage(),
    loadMovementsPage(),
    loadLocationsPage(),
    loadMorePage(),
    loadAdminUsersPage(),
  ]);
}
