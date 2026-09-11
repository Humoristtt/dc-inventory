import { Link, Outlet, useLocation } from "react-router-dom";

import { useAuthState } from "../features/auth/useAuthState";
import { useTelegramNavigation } from "../features/navigation/useTelegramNavigation";
import { hasAnyCapability } from "../shared/api/auth";
import "./styles/app-shell.css";
import { RouteContent } from "./RouteContent";

const navigationItems = [
  { to: "/catalog", label: "Каталог", icon: "▦" },
  { to: "/movements", label: "Движения", icon: "↔" },
  { to: "/more", label: "Ещё", icon: "•••" },
] as const;

function isActive(pathname: string, target: string): boolean {
  if (target === "/catalog") {
    return pathname === "/catalog" || pathname.startsWith("/catalog/");
  }

  if (target === "/more") {
    return pathname === "/more" || pathname.startsWith("/more/");
  }

  return pathname === target;
}

export function ApplicationShell() {
  const auth = useAuthState();
  const location = useLocation();
  useTelegramNavigation();

  const canReadMovements = hasAnyCapability(
    auth.data?.user,
    ["movement.read_own", "movement.read_all"],
  );

  const visibleNavigationItems = navigationItems.filter(
    (item) => item.to !== "/movements" || canReadMovements,
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
            const active = isActive(location.pathname, item.to);

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
