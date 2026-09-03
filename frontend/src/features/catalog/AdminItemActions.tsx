import {
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { CatalogItem } from "../../shared/api/catalog";
import { setCatalogItemArchived } from "../../shared/api/catalog";
import { useAuthState } from "../auth/useAuthState";
import "./admin-catalog.css";

export function AdminItemActions({ item }: { item: CatalogItem }) {
  const authQuery = useAuthState();
  const queryClient = useQueryClient();
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const mutation = useMutation({
    mutationFn: () => setCatalogItemArchived(item.id, item.status === "ACTIVE"),
    onSuccess: (updated) => {
      queryClient.setQueryData(["catalog", "item", item.id], updated);
      void queryClient.invalidateQueries({ queryKey: ["catalog", "items"] });
      setConfirmationOpen(false);
    },
  });

  if (authQuery.data?.user.role !== "ADMIN") {
    return null;
  }

  return (
    <section aria-labelledby="admin-actions-title" className="detail-panel admin-item-actions">
      <div className="detail-panel__heading">
        <div>
          <span className="section-kicker">ADMIN</span>
          <h2 id="admin-actions-title">Управление позицией</h2>
        </div>
      </div>
      <div className="admin-item-actions__buttons">
        <Link
          className="button button--dark"
          state={{ from: `/catalog/items/${item.id}` }}
          to={`/catalog/items/${encodeURIComponent(item.id)}/edit`}
        >
          Редактировать
        </Link>
        <button
          className={item.status === "ACTIVE" ? "button button--danger" : "button button--ghost"}
          disabled={mutation.isPending}
          onClick={() => setConfirmationOpen(true)}
          type="button"
        >
          {item.status === "ACTIVE" ? "В архив" : "Вернуть из архива"}
        </button>
      </div>
      {mutation.isError ? (
        <p className="admin-item-actions__error" role="alert">
          Не удалось изменить статус. Повторите попытку.
        </p>
      ) : null}

      {confirmationOpen ? (
        <div className="sheet-backdrop" role="presentation">
          <section aria-labelledby="archive-title" aria-modal="true" className="sheet archive-sheet" role="dialog">
            <header className="sheet__header">
              <div>
                <span className="section-kicker">Подтверждение</span>
                <h2 id="archive-title">
                  {item.status === "ACTIVE" ? "Архивировать позицию?" : "Вернуть позицию?"}
                </h2>
              </div>
              <button aria-label="Закрыть подтверждение" className="icon-button" onClick={() => setConfirmationOpen(false)} type="button">×</button>
            </header>
            <div className="sheet__body archive-sheet__body">
              {item.status === "ACTIVE" ? (
                <p>Позиция исчезнет из активного каталога. Текущий складской остаток, оборудование у сотрудников и история движений не удаляются.</p>
              ) : (
                <p>Позиция снова появится в активном каталоге. Складские данные останутся без изменений.</p>
              )}
            </div>
            <footer className="sheet__footer">
              <button className="button button--ghost" disabled={mutation.isPending} onClick={() => setConfirmationOpen(false)} type="button">Отмена</button>
              <button className="button button--dark" disabled={mutation.isPending} onClick={() => mutation.mutate()} type="button">
                {mutation.isPending ? "Сохраняем…" : "Подтвердить"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </section>
  );
}
