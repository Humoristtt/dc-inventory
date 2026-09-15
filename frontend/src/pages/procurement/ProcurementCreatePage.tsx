import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { LineComposer } from "../../features/procurement/LineComposer";
import { useAuthState } from "../../features/auth/useAuthState";
import { hasCapability } from "../../shared/api/auth";
import {
  createProcurementRequest,
  getProcurementManagers,
  procurementError,
  type ProcurementLineInput,
} from "../../shared/api/procurement";
import { PageHeader } from "../../shared/ui";
import "../../features/procurement/procurement.css";

export function ProcurementCreatePage() {
  const auth = useAuthState();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [manager, setManager] = useState("");
  const [managerSearch, setManagerSearch] = useState("");
  const [comment, setComment] = useState("");
  const [lines, setLines] = useState<ProcurementLineInput[]>([]);
  const submissionIntentRef = useRef<{
    fingerprint: string;
    clientRequestId: string;
  } | null>(null);
  const canCreate = hasCapability(auth.data?.user, "procurement.create");
  const managers = useInfiniteQuery({
    queryKey: [
      "procurement",
      "managers",
      managerSearch,
    ],
    queryFn: ({ pageParam, signal }) =>
      getProcurementManagers(
        {
          q: managerSearch,
          limit: 50,
          offset: pageParam,
        },
        signal,
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const nextOffset =
        lastPage.offset
        + lastPage.items.length;

      return nextOffset < lastPage.total
        ? nextOffset
        : undefined;
    },
    enabled: !auth.isPending && canCreate,
  });

  const managerOptions =
    managers.data?.pages.flatMap(
      (page) => page.items,
    )
    ?? [];
  const mutation = useMutation({
    mutationFn: () => {
      const submission = {
        assigned_manager_user_id: manager,
        general_comment: comment.trim() || null,
        lines: lines.map((line) =>
          line.line_type === "EXISTING_ITEM"
            ? {
                line_type: line.line_type,
                item_id: line.item_id,
                quantity: line.quantity,
              }
            : line,
        ),
      };

      const fingerprint = JSON.stringify(submission);
      let intent = submissionIntentRef.current;

      if (
        intent === null
        || intent.fingerprint !== fingerprint
      ) {
        intent = {
          fingerprint,
          clientRequestId: crypto.randomUUID(),
        };
        submissionIntentRef.current = intent;
      }

      return createProcurementRequest({
        ...submission,
        client_request_id: intent.clientRequestId,
      });
    },
    onSuccess: (request) => {
      void queryClient.invalidateQueries({ queryKey: ["procurement"] });
      navigate(`/procurement/${request.id}`, { replace: true });
    },
  });

  if (auth.isPending) return <p role="status">Загрузка…</p>;
  if (!canCreate) {
    return <Navigate replace to="/catalog" />;
  }

  return (
    <main className="procurement-page">
      <PageHeader kicker="Закупки" title="Новая заявка" />
      <form
        className="procurement-page__body form-surface"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          if (manager && lines.length) mutation.mutate();
        }}
      >
        <section className="detail-panel procurement-fields">
          <h2>Ответственный</h2>
          <label>
            Поиск менеджера
            <input
              value={managerSearch}
              onChange={(event) => {
                setManagerSearch(
                  event.target.value,
                );
                setManager("");
              }}
            />
          </label>

          <label>
            Менеджер
            <select
              value={manager}
              onChange={(event) =>
                setManager(
                  event.target.value,
                )}
            >
              <option value="">
                Выберите менеджера
              </option>
              {managerOptions.map(
                (entry) => (
                  <option
                    key={entry.id}
                    value={entry.id}
                  >
                    {entry.display_name}
                  </option>
                ),
              )}
            </select>
          </label>

          {managers.hasNextPage ? (
            <button
              className="button button--load-more"
              disabled={
                managers.isFetchingNextPage
              }
              onClick={() =>
                void managers.fetchNextPage()
              }
              type="button"
            >
              {managers.isFetchingNextPage
                ? "Загружаем менеджеров…"
                : "Показать ещё менеджеров"}
            </button>
          ) : null}
          <label>
            Общий комментарий
            <textarea
              maxLength={4000}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
        </section>
        <LineComposer lines={lines} onChange={setLines} />
        {mutation.isError ? <p role="alert">{procurementError(mutation.error)}</p> : null}
        <button
          className="button button--dark procurement-primary"
          disabled={!manager || !lines.length || mutation.isPending}
          type="submit"
        >
          {mutation.isPending ? "Отправляем…" : "Отправить заявку"}
        </button>
      </form>
    </main>
  );
}
