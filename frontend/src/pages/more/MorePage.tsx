import { Link } from "react-router-dom";

import { useAuthState } from "../../features/auth/useAuthState";
import "../../features/admin/access-admin.css";
import { PageHeader } from "../../shared/ui";

export function MorePage() {
  const auth = useAuthState();
  const admin = auth.data?.user.role === "ADMIN";

  return (
    <main className="more-page">
      <PageHeader
        kicker="Управление"
        title="Ещё"
      />

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
