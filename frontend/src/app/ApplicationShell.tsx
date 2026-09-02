import { Link, Outlet, useLocation } from "react-router-dom";

import { useTelegramNavigation } from "../features/navigation/useTelegramNavigation";
import "./styles/app-shell.css";

const navigationItems = [
  { to: "/catalog", label: "Каталог", icon: "▦" },
  { to: "/mine", label: "Моё", icon: "◎" },
  { to: "/movements", label: "Движения", icon: "↔" },
  { to: "/more", label: "Ещё", icon: "•••" },
] as const;

function isActive(pathname: string, target: string): boolean {
  if (target === "/catalog") {
    return pathname === "/catalog" || pathname.startsWith("/catalog/");
  }
  return pathname === target;
}

export function ApplicationShell() {
  const location = useLocation();
  useTelegramNavigation();

  return (
    <div className="app-shell">
      <div className="app-shell__content">
        <Outlet />
      </div>
      <nav aria-label="Основная навигация" className="bottom-nav">
        <div className="bottom-nav__inner">
          {navigationItems.map((item) => {
            const active = isActive(location.pathname, item.to);
            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={active ? "bottom-nav__item bottom-nav__item--active" : "bottom-nav__item"}
                key={item.to}
                to={item.to}
              >
                <span className="bottom-nav__icon" aria-hidden="true">{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
