import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
  const [comment, setComment] = useState("");
  const [lines, setLines] = useState<ProcurementLineInput[]>([]);
  const managers = useQuery({
    queryKey: ["procurement", "managers"],
    queryFn: ({ signal }) => getProcurementManagers(signal),
  });
  const mutation = useMutation({
    mutationFn: () =>
      createProcurementRequest({
        assigned_manager_user_id: manager,
        general_comment: comment.trim() || null,
        client_request_id: crypto.randomUUID(),
        lines,
      }),
    onSuccess: (request) => {
      void queryClient.invalidateQueries({ queryKey: ["procurement"] });
      navigate(`/procurement/${request.id}`, { replace: true });
    },
  });

  if (auth.isPending) return <p role="status">Загрузка…</p>;
  if (!hasCapability(auth.data?.user, "procurement.create")) {
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
            Менеджер
            <select value={manager} onChange={(event) => setManager(event.target.value)}>
              <option value="">Выберите менеджера</option>
              {(managers.data?.items ?? []).map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.display_name}
                </option>
              ))}
            </select>
          </label>
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
