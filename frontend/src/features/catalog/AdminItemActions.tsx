import {
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { useState } from "react";
import {
  Link,
  useNavigate,
} from "react-router-dom";

import type { CatalogItem } from "../../shared/api/catalog";
import {
  deleteCatalogItem,
  setCatalogItemArchived,
} from "../../shared/api/catalog";
import {
  ApiRequestError,
  hasCapability,
} from "../../shared/api/auth";
import { useAuthState } from "../auth/useAuthState";
import "./admin-catalog.css";

type ConfirmationAction = "archive" | "delete";

export function AdminItemActions({ item }: { item: CatalogItem }) {
  const authQuery = useAuthState();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [confirmation, setConfirmation] =
    useState<ConfirmationAction | null>(null);

  const user = authQuery.data?.user;
  const canEdit = hasCapability(user, "catalog.manage");
  const canArchive = hasCapability(user, "catalog.archive");
  const canDelete = hasCapability(
    user,
    "catalog.delete_unused",
  );

  const archiveMutation = useMutation({
    mutationFn: () =>
      setCatalogItemArchived(
        item.id,
        item.status === "ACTIVE",
      ),
    onSuccess: (updated) => {
      queryClient.setQueryData(
        ["catalog", "item", item.id],
        updated,
      );
      void queryClient.invalidateQueries({
        queryKey: ["catalog", "items"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["catalog", "facets"],
      });
      setConfirmation(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteCatalogItem(item.id),
    onSuccess: () => {
      queryClient.removeQueries({
        queryKey: ["catalog", "item", item.id],
      });
      void queryClient.invalidateQueries({
        queryKey: ["catalog", "items"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["catalog", "facets"],
      });
      setConfirmation(null);
      navigate(
        `/catalog/${encodeURIComponent(
          item.category.key,
        )}`,
        { replace: true },
      );
    },
  });

  if (!canEdit && !canArchive && !canDelete) {
    return null;
  }

  const deleteError =
    deleteMutation.error instanceof ApiRequestError
    && deleteMutation.error.code === "catalog_item_in_use"
      ? "Удалить нельзя: позиция уже использовалась в складском учёте."
      : "Не удалось удалить позицию. Повторите попытку.";

  const anyMutationPending =
    archiveMutation.isPending || deleteMutation.isPending;

  return (
    <section
      aria-labelledby="admin-actions-title"
      className="detail-panel admin-item-actions"
    >
      <div className="detail-panel__heading">
        <div>
          <span className="section-kicker">
            Управление
          </span>
          <h2 id="admin-actions-title">
            Управление позицией
          </h2>
        </div>
      </div>

      <div className="admin-item-actions__buttons">
        {canEdit ? (
          <Link
            className="button button--dark"
            state={{
              from: `/catalog/items/${item.id}`,
            }}
            to={`/catalog/items/${encodeURIComponent(
              item.id,
            )}/edit`}
          >
            Редактировать
          </Link>
        ) : null}

        {canArchive ? (
          <button
            className={
              item.status === "ACTIVE"
                ? "button button--danger"
                : "button button--ghost"
            }
            disabled={anyMutationPending}
            onClick={() =>
              setConfirmation("archive")
            }
            type="button"
          >
            {item.status === "ACTIVE"
              ? "В архив"
              : "Вернуть из архива"}
          </button>
        ) : null}

        {canDelete ? (
          <button
            className="button button--danger"
            disabled={anyMutationPending}
            onClick={() =>
              setConfirmation("delete")
            }
            type="button"
          >
            Удалить позицию
          </button>
        ) : null}
      </div>

      {archiveMutation.isError ? (
        <p
          className="admin-item-actions__error"
          role="alert"
        >
          Не удалось изменить статус. Повторите
          попытку.
        </p>
      ) : null}

      {deleteMutation.isError ? (
        <p
          className="admin-item-actions__error"
          role="alert"
        >
          {deleteError}
        </p>
      ) : null}

      {confirmation === "archive" ? (
        <div
          className="sheet-backdrop"
          role="presentation"
        >
          <section
            aria-labelledby="archive-title"
            aria-modal="true"
            className="sheet archive-sheet"
            role="dialog"
          >
            <header className="sheet__header">
              <div>
                <span className="section-kicker">
                  Подтверждение
                </span>
                <h2 id="archive-title">
                  {item.status === "ACTIVE"
                    ? "Архивировать позицию?"
                    : "Вернуть позицию?"}
                </h2>
              </div>
              <button
                aria-label="Закрыть подтверждение"
                className="icon-button"
                data-escape-dismiss=""
                onClick={() =>
                  setConfirmation(null)
                }
                type="button"
              >
                ×
              </button>
            </header>

            <div className="sheet__body archive-sheet__body">
              {item.status === "ACTIVE" ? (
                <p>
                  Позиция исчезнет из активного
                  каталога. Складской остаток и
                  история движений сохранятся.
                </p>
              ) : (
                <p>
                  Позиция снова появится в активном
                  каталоге. Складские данные
                  останутся без изменений.
                </p>
              )}
            </div>

            <footer className="sheet__footer">
              <button
                className="button button--ghost"
                disabled={archiveMutation.isPending}
                onClick={() =>
                  setConfirmation(null)
                }
                type="button"
              >
                Отмена
              </button>
              <button
                className="button button--dark"
                disabled={archiveMutation.isPending}
                onClick={() =>
                  archiveMutation.mutate()
                }
                type="button"
              >
                {archiveMutation.isPending
                  ? "Сохраняем…"
                  : "Подтвердить"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}

      {confirmation === "delete" ? (
        <div
          className="sheet-backdrop"
          role="presentation"
        >
          <section
            aria-labelledby="delete-item-title"
            aria-modal="true"
            className="sheet archive-sheet"
            role="dialog"
          >
            <header className="sheet__header">
              <div>
                <span className="section-kicker">
                  Необратимое действие
                </span>
                <h2 id="delete-item-title">
                  Удалить позицию безвозвратно?
                </h2>
              </div>
              <button
                aria-label="Закрыть подтверждение"
                className="icon-button"
                data-escape-dismiss=""
                onClick={() =>
                  setConfirmation(null)
                }
                type="button"
              >
                ×
              </button>
            </header>

            <div className="sheet__body archive-sheet__body">
              <p>
                Удаление разрешено только для
                позиции, которая никогда не
                участвовала в складском учёте.
                Исторические позиции удалять
                нельзя.
              </p>
            </div>

            <footer className="sheet__footer">
              <button
                className="button button--ghost"
                disabled={deleteMutation.isPending}
                onClick={() =>
                  setConfirmation(null)
                }
                type="button"
              >
                Отмена
              </button>
              <button
                className="button button--danger"
                disabled={deleteMutation.isPending}
                onClick={() =>
                  deleteMutation.mutate()
                }
                type="button"
              >
                {deleteMutation.isPending
                  ? "Удаляем…"
                  : "Удалить безвозвратно"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </section>
  );
}
