import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { useAuthState } from "../../features/auth/useAuthState";
import { hasCapability } from "../../shared/api/auth";
import { getProcurementRequests } from "../../shared/api/procurement";
import { PageHeader } from "../../shared/ui";
import "../../features/procurement/procurement.css";

type View = "my" | "active" | "history";

const pageSize = 30;

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

  const list = useInfiniteQuery({
    queryKey: ["procurement", "requests", view],
    queryFn: ({ pageParam, signal }) =>
      getProcurementRequests(
        view,
        {
          limit: pageSize,
          offset: pageParam,
        },
        signal,
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const nextOffset =
        lastPage.offset + lastPage.items.length;

      return nextOffset < lastPage.total
        ? nextOffset
        : undefined;
    },
    enabled: !auth.isPending && canReadProcurement,
  });

  const items =
    list.data?.pages.flatMap((page) => page.items)
    ?? [];

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
        <div
          aria-label="Очередь закупок"
          className="procurement-tabs"
          role="tablist"
        >
          {manager ? (
            <button
              aria-selected={view === "my"}
              onClick={() => setSelectedView("my")}
              role="tab"
              type="button"
            >
              Мои
            </button>
          ) : null}
          <button
            aria-selected={view === "active"}
            onClick={() => setSelectedView("active")}
            role="tab"
            type="button"
          >
            {manager ? "Все активные" : "Активные"}
          </button>
          <button
            aria-selected={view === "history"}
            onClick={() => setSelectedView("history")}
            role="tab"
            type="button"
          >
            История
          </button>
        </div>

        {list.isPending ? (
          <p role="status">Загружаем заявки…</p>
        ) : null}

        {list.isError ? (
          <p role="alert">
            Не удалось загрузить заявки.{" "}
            <button
              onClick={() => void list.refetch()}
              type="button"
            >
              Повторить
            </button>
          </p>
        ) : null}

        {!list.isPending
        && !list.isError
        && items.length === 0 ? (
          <p className="empty-state">
            В этой очереди пока нет заявок.
          </p>
        ) : null}

        <div className="procurement-list">
          {items.map((entry) => (
            <Link
              className="procurement-card"
              key={entry.id}
              to={`/procurement/${entry.id}`}
            >
              <div>
                <strong>{entry.request_number}</strong>
                <span className="procurement-status">
                  {entry.status_label}
                </span>
              </div>
              <p>
                Редакция {entry.revision_number}
                {" · "}
                {entry.line_count} поз.
              </p>
              <p>
                Менеджер: {entry.assigned_manager.display_name}
              </p>
            </Link>
          ))}
        </div>

        {list.hasNextPage ? (
          <button
            className="button button--load-more"
            disabled={list.isFetchingNextPage}
            onClick={() => void list.fetchNextPage()}
            type="button"
          >
            {list.isFetchingNextPage
              ? "Загружаем…"
              : "Показать ещё"}
          </button>
        ) : null}
      </div>
    </main>
  );
}
