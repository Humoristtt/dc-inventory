import {
  lazy,
  type ComponentType,
  type LazyExoticComponent,
} from "react";
import {
  matchRoutes,
  type RouteObject,
} from "react-router-dom";

import {
  type AuthUser,
  type Capability,
  hasAnyCapability,
} from "../shared/api/auth";
import {
  loadAdminUsersPage,
  loadCatalogLandingPage,
  loadCategoryPage,
  loadItemDetailPage,
  loadItemFormPage,
  loadLocationsPage,
  loadMorePage,
  loadMovementsPage,
  loadProcurementCreatePage,
  loadProcurementDetailPage,
  loadProcurementListPage,
} from "./routeModules";

export const APP_DEFAULT_PATH = "/catalog";

type RouteLoader = () => Promise<{
  default: ComponentType;
}>;

type NavigationMetadata = {
  label: string;
  icon: string;
  requiredAny?: readonly Capability[];
};

export type AppRouteDefinition = {
  id: string;
  path: string;
  component: LazyExoticComponent<ComponentType>;
  loader: RouteLoader;
  navigation?: NavigationMetadata;
};

export type PrimaryNavigationItem = {
  routeId: string;
  to: string;
  label: string;
  icon: string;
  requiredAny?: readonly Capability[];
};

function route(
  id: string,
  path: string,
  loader: RouteLoader,
  navigation?: NavigationMetadata,
): AppRouteDefinition {
  return {
    id,
    path,
    loader,
    component: lazy(loader),
    ...(navigation === undefined
      ? {}
      : { navigation }),
  };
}

export const APP_ROUTES: readonly AppRouteDefinition[] = [
  route(
    "catalog",
    "/catalog",
    loadCatalogLandingPage,
    {
      label: "Каталог",
      icon: "▦",
    },
  ),
  route(
    "catalog-new",
    "/catalog/new",
    loadItemFormPage,
  ),
  route(
    "catalog-edit",
    "/catalog/items/:itemId/edit",
    loadItemFormPage,
  ),
  route(
    "catalog-item",
    "/catalog/items/:itemId",
    loadItemDetailPage,
  ),
  route(
    "catalog-category",
    "/catalog/:categoryKey",
    loadCategoryPage,
  ),
  route(
    "movements",
    "/movements",
    loadMovementsPage,
    {
      label: "Движения",
      icon: "↔",
      requiredAny: [
        "movement.read_own",
        "movement.read_all",
      ],
    },
  ),
  route(
    "procurement",
    "/procurement",
    loadProcurementListPage,
    {
      label: "Закупки",
      icon: "◫",
      requiredAny: ["procurement.read"],
    },
  ),
  route(
    "procurement-new",
    "/procurement/new",
    loadProcurementCreatePage,
  ),
  route(
    "procurement-detail",
    "/procurement/:requestId",
    loadProcurementDetailPage,
  ),
  route(
    "more",
    "/more",
    loadMorePage,
    {
      label: "Ещё",
      icon: "•••",
    },
  ),
  route(
    "locations",
    "/more/locations",
    loadLocationsPage,
  ),
  route(
    "admin-users",
    "/more/users",
    loadAdminUsersPage,
  ),
] as const;

export const PRIMARY_NAVIGATION: readonly PrimaryNavigationItem[] =
  APP_ROUTES.flatMap((definition) => {
    if (definition.navigation === undefined) {
      return [];
    }

    return [{
      routeId: definition.id,
      to: definition.path,
      ...definition.navigation,
    }];
  });

const ROUTE_MATCHERS: RouteObject[] =
  APP_ROUTES.map((definition) => ({
    id: definition.id,
    path: definition.path,
    handle: definition,
  }));

function routeById(
  routeId: string,
): AppRouteDefinition | undefined {
  return APP_ROUTES.find(
    (definition) =>
      definition.id === routeId,
  );
}

export function routeForPath(
  pathname: string,
): AppRouteDefinition | undefined {
  if (pathname === "/") {
    return routeById("catalog");
  }

  const matches = matchRoutes(
    ROUTE_MATCHERS,
    pathname,
  );

  const match = matches?.at(-1);

  return match?.route.handle as
    | AppRouteDefinition
    | undefined;
}

export function isNavigationItemVisible(
  item: PrimaryNavigationItem,
  user:
    | Pick<AuthUser, "capabilities">
    | null
    | undefined,
): boolean {
  if (item.requiredAny === undefined) {
    return true;
  }

  return hasAnyCapability(
    user,
    item.requiredAny,
  );
}

export function isNavigationItemActive(
  pathname: string,
  item: PrimaryNavigationItem,
): boolean {
  return pathname === item.to
    || pathname.startsWith(
      `${item.to}/`,
    );
}

export async function preloadRouteForPath(
  pathname: string,
): Promise<void> {
  const loader =
    routeForPath(pathname)?.loader;

  if (loader === undefined) {
    return;
  }

  try {
    await loader();
  } catch {
    // RouteContent is the runtime recovery boundary for chunk failures.
  }
}
