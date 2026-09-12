import { Link } from "react-router-dom";

import "../../features/admin/access-admin.css";
import { useAuthState } from "../../features/auth/useAuthState";
import { hasCapability } from "../../shared/api/auth";
import { PageHeader } from "../../shared/ui";

export function MorePage() {
  const auth = useAuthState();
  const canManageUsers = hasCapability(
    auth.data?.user,
    "access.manage_users",
  );

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
            <span>
              Склады, ЦОД и адреса размещения оборудования
            </span>
          </Link>

          {canManageUsers ? (
            <Link className="more-card" to="/more/users">
              <strong>Пользователи</strong>
              <span>
                Роли, доступ и история изменений
              </span>
            </Link>
          ) : null}
        </div>
      </div>
    </main>
  );
}
