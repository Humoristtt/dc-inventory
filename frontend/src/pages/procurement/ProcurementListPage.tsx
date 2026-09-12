import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { useAuthState } from "../../features/auth/useAuthState";
import { hasCapability } from "../../shared/api/auth";
import { getProcurementRequests } from "../../shared/api/procurement";
import { PageHeader } from "../../shared/ui";
import "../../features/procurement/procurement.css";

type View = "my" | "active" | "history";

export function ProcurementListPage() {
  const auth = useAuthState();
  const canReadProcurement = hasCapability(
    auth.data?.user,
    "procurement.read",
  );
  const manager = hasCapability(
    auth.data?.user,
    "procurement.manage",
  );
  const [selectedView, setSelectedView] = useState<View | null>(null);
  const view = selectedView ?? (manager ? "my" : "active");

  const list = useQuery({
    queryKey: ["procurement", "requests", view],
    queryFn: ({ signal }) => getProcurementRequests(view, signal),
    enabled: !auth.isPending && canReadProcurement,
  });

  if (auth.isPending) return <p role="status">Загрузка…</p>;
  if (!canReadProcurement) {
    return <Navigate replace to="/catalog" />;
  }

  return (
    <main className="procurement-page">
      <PageHeader
        actions={
          hasCapability(auth.data?.user, "procurement.create") ? (
            <Link className="button button--accent" to="/procurement/new">
              Новая заявка
            </Link>
          ) : undefined
        }
        kicker="Снабжение"
        title="Закупки"
      />
      <div className="procurement-page__body">
        <div className="procurement-tabs" role="tablist" aria-label="Очередь закупок">
          {manager ? (
            <button role="tab" onClick={() => setSelectedView("my")} aria-selected={view === "my"} type="button">
              Мои
            </button>
          ) : null}
          <button role="tab" onClick={() => setSelectedView("active")} aria-selected={view === "active"} type="button">
            {manager ? "Все активные" : "Активные"}
          </button>
          <button role="tab" onClick={() => setSelectedView("history")} aria-selected={view === "history"} type="button">
            История
          </button>
        </div>
        {list.isPending ? <p role="status">Загружаем заявки…</p> : null}
        {list.isError ? (
          <p role="alert">
            Не удалось загрузить заявки.{" "}
            <button onClick={() => void list.refetch()} type="button">Повторить</button>
          </p>
        ) : null}
        {list.data?.items.length === 0 ? (
          <p className="empty-state">В этой очереди пока нет заявок.</p>
        ) : null}
        <div className="procurement-list">
          {(list.data?.items ?? []).map((entry) => (
            <Link className="procurement-card" key={entry.id} to={`/procurement/${entry.id}`}>
              <div>
                <strong>{entry.request_number}</strong>
                <span className="procurement-status">{entry.status_label}</span>
              </div>
              <p>Редакция {entry.revision_number} · {entry.line_count} поз.</p>
              <p>Менеджер: {entry.assigned_manager.display_name}</p>
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}
