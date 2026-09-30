import {
  lazy,
  type ComponentType,
  type LazyExoticComponent,
} from "react";
import { matchPath } from "react-router-dom";

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

type RouteAccessPolicy = {
  anyOf: readonly Capability[];
  redirectTo: string;
};

export type AppRouteDefinition = {
  id: string;
  path: string;
  component: LazyExoticComponent<ComponentType>;
  loader: RouteLoader;
  access?: RouteAccessPolicy;
};

type NavigationItem = {
  routeId: string;
  to: string;
  label: string;
  icon: string;
};

function route(
  id: string,
  path: string,
  loader: RouteLoader,
  access?: RouteAccessPolicy,
): AppRouteDefinition {
  return {
    id,
    path,
    loader,
    component: lazy(loader),
    ...(access === undefined ? {} : { access }),
  };
}

export const APP_ROUTES: readonly AppRouteDefinition[] = [
  route(
    "catalog",
    "/catalog",
    loadCatalogLandingPage,
  ),
  route(
    "catalog-new",
    "/catalog/new",
    loadItemFormPage,
    {
      anyOf: ["catalog.manage"],
      redirectTo: APP_DEFAULT_PATH,
    },
  ),
  route(
    "catalog-edit",
    "/catalog/items/:itemId/edit",
    loadItemFormPage,
    {
      anyOf: ["catalog.manage"],
      redirectTo: APP_DEFAULT_PATH,
    },
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
      anyOf: [
        "movement.read_own",
        "movement.read_all",
      ],
      redirectTo: APP_DEFAULT_PATH,
    },
  ),
  route(
    "procurement",
    "/procurement",
    loadProcurementListPage,
    {
      anyOf: ["procurement.read"],
      redirectTo: APP_DEFAULT_PATH,
    },
  ),
  route(
    "procurement-new",
    "/procurement/new",
    loadProcurementCreatePage,
    {
      anyOf: ["procurement.create"],
      redirectTo: APP_DEFAULT_PATH,
    },
  ),
  route(
    "procurement-detail",
    "/procurement/:requestId",
    loadProcurementDetailPage,
    {
      anyOf: ["procurement.read"],
      redirectTo: APP_DEFAULT_PATH,
    },
  ),
  route(
    "more",
    "/more",
    loadMorePage,
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
    {
      anyOf: ["access.manage_users"],
      redirectTo: "/more",
    },
  ),
] as const;

export const PRIMARY_NAVIGATION: readonly NavigationItem[] = [
  {
    routeId: "catalog",
    to: "/catalog",
    label: "Каталог",
    icon: "▦",
  },
  {
    routeId: "movements",
    to: "/movements",
    label: "Движения",
    icon: "↔",
  },
  {
    routeId: "procurement",
    to: "/procurement",
    label: "Закупки",
    icon: "◫",
  },
  {
    routeId: "more",
    to: "/more",
    label: "Ещё",
    icon: "•••",
  },
] as const;

function routeById(routeId: string): AppRouteDefinition {
  const definition = APP_ROUTES.find(
    (candidate) => candidate.id === routeId,
  );

  if (definition === undefined) {
    throw new Error(`unknown application route: ${routeId}`);
  }

  return definition;
}

export function routeForPath(
  pathname: string,
): AppRouteDefinition | undefined {
  if (pathname === "/") {
    return routeById("catalog");
  }

  return APP_ROUTES.find((definition) =>
    matchPath(
      {
        path: definition.path,
        end: true,
      },
      pathname,
    ) !== null,
  );
}

export function routeAccessRedirect(
  pathname: string,
  user: Pick<AuthUser, "capabilities"> | null | undefined,
): string | undefined {
  const access = routeForPath(pathname)?.access;

  if (
    access === undefined
    || hasAnyCapability(user, access.anyOf)
  ) {
    return undefined;
  }

  return access.redirectTo;
}

export function isNavigationItemVisible(
  item: NavigationItem,
  user: Pick<AuthUser, "capabilities"> | null | undefined,
): boolean {
  const access = routeById(item.routeId).access;

  return access === undefined
    || hasAnyCapability(user, access.anyOf);
}

export function isNavigationItemActive(
  pathname: string,
  item: NavigationItem,
): boolean {
  return pathname === item.to
    || pathname.startsWith(`${item.to}/`);
}

export async function preloadRouteForPath(
  pathname: string,
): Promise<void> {
  const loader = routeForPath(pathname)?.loader;

  if (loader === undefined) {
    return;
  }

  try {
    await loader();
  } catch {
    // RouteContent remains the recovery boundary for a real chunk failure.
  }
}
