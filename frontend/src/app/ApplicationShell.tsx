import { useEffect, useRef } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";

import { useAuthState } from "../features/auth/useAuthState";
import { useTelegramNavigation } from "../features/navigation/useTelegramNavigation";
import { hasAnyCapability } from "../shared/api/auth";
import "./styles/app-shell.css";
import { RouteContent } from "./RouteContent";

const navigationItems = [
  { to: "/catalog", label: "Каталог", icon: "▦" },
  { to: "/movements", label: "Движения", icon: "↔" },
  { to: "/procurement", label: "Закупки", icon: "◫" },
  { to: "/more", label: "Ещё", icon: "•••" },
] as const;

function isActive(pathname: string, target: string): boolean {
  if (target === "/catalog") {
    return pathname === "/catalog" || pathname.startsWith("/catalog/");
  }

  if (target === "/more") {
    return pathname === "/more" || pathname.startsWith("/more/");
  }

  if (target === "/procurement") {
    return pathname === target || pathname.startsWith("/procurement/");
  }

  return pathname === target;
}

export function ApplicationShell() {
  const auth = useAuthState();
  const location = useLocation();
  const contentRef = useRef<HTMLDivElement>(null);
  useTelegramNavigation();

  // Desktop scroll lives inside the content row to keep the footer from
  // covering cards. A new route must start at its own top, not at the previous
  // page's scroll position; mobile continues to use window scrolling.
  useEffect(() => {
    if (contentRef.current !== null) {
      contentRef.current.scrollTop = 0;
      contentRef.current.scrollLeft = 0;
    }
  }, [location.pathname]);

  const canReadMovements = hasAnyCapability(
    auth.data?.user,
    ["movement.read_own", "movement.read_all"],
  );
  const canReadProcurement = hasAnyCapability(
    auth.data?.user,
    ["procurement.read"],
  );

  const visibleNavigationItems = navigationItems.filter(
    (item) =>
      (item.to !== "/movements" || canReadMovements)
      && (item.to !== "/procurement" || canReadProcurement),
  );

  return (
    <div className="app-shell">
      <div className="app-shell__content" ref={contentRef}>
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
