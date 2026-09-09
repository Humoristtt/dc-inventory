import { Link } from "react-router-dom";

import { useAuthState } from "../../features/auth/useAuthState";
import "../../features/admin/access-admin.css";
import { SpikatelBrand } from "../../shared/brand/SpikatelBrand";
import { TelegramFullscreenButton } from "../../shared/telegram/TelegramFullscreenButton";

export function MorePage() {
  const auth = useAuthState();
  const admin = auth.data?.user.role === "ADMIN";

  return (
    <main className="more-page">
      <header className="more-page__header">
        <div className="more-page__toolbar">
          <SpikatelBrand inverse title="Инвентаризация ЦОД" />
          <TelegramFullscreenButton />
        </div>

        <div>
          <span className="more-page__kicker">Управление</span>
          <h1>Ещё</h1>
        </div>
      </header>

      <div className="more-page__body">
        <div className="more-grid">
          <Link className="more-card" to="/more/locations">
            <strong>Места хранения</strong>
            <span>Склады, ЦОД и адреса размещения оборудования</span>
          </Link>

          {admin ? (
            <Link className="more-card" to="/more/users">
              <strong>Пользователи</strong>
              <span>Просмотр, блокировка и восстановление доступа</span>
            </Link>
          ) : null}
        </div>
      </div>
    </main>
  );
}
