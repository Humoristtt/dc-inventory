import {
  Link,
  Navigate,
  Outlet,
  useLocation,
} from "react-router-dom";

import { useAuthState } from "../features/auth/useAuthState";
import { useTelegramNavigation } from "../features/navigation/useTelegramNavigation";
import "./styles/app-shell.css";
import {
  isNavigationItemActive,
  isNavigationItemVisible,
  PRIMARY_NAVIGATION,
  routeAccessRedirect,
} from "./appRoutes";
import { RouteContent } from "./RouteContent";

export function ApplicationShell() {
  const auth = useAuthState();
  const location = useLocation();
  useTelegramNavigation();

  const accessRedirect = auth.data === undefined
    ? undefined
    : routeAccessRedirect(
        location.pathname,
        auth.data.user,
      );

  if (accessRedirect !== undefined) {
    return (
      <Navigate
        replace
        to={accessRedirect}
      />
    );
  }

  const visibleNavigationItems = PRIMARY_NAVIGATION.filter(
    (item) =>
      isNavigationItemVisible(
        item,
        auth.data?.user,
      ),
  );

  return (
    <div className="app-shell">
      <div className="app-shell__content">
        <RouteContent resetKey={location.pathname}>
          <Outlet />
        </RouteContent>
      </div>

      <nav aria-label="Основная навигация" className="bottom-nav">
        <div className="bottom-nav__inner">
          {visibleNavigationItems.map((item) => {
            const active = isNavigationItemActive(
              location.pathname,
              item,
            );

            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={
                  active
                    ? "bottom-nav__item bottom-nav__item--active"
                    : "bottom-nav__item"
                }
                key={item.to}
                to={item.to}
              >
                <span
                  className="bottom-nav__icon"
                  aria-hidden="true"
                >
                  {item.icon}
                </span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
