import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { AdminUser } from "../../shared/api/adminUsers";
import "./user-account-reset.css";

const CONFIRMATION = "СБРОСИТЬ";

type Props = {
  user: AdminUser;
  currentUserId: string | undefined;
  canAssignAdmin: boolean;
};

async function resetAccount(user: AdminUser): Promise<void> {
  const response = await fetch(
    `/api/admin/users/${encodeURIComponent(user.id)}/reset`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        telegram_user_id: user.telegram_user_id,
        confirmation: CONFIRMATION,
      }),
    },
  );

  if (response.status === 204) return;

  let code = "";
  if (!response.ok) {
    try {
      const data = (await response.json()) as {
        detail?: { code?: string };
      };
      code = data.detail?.code ?? "";
    } catch {
      // A failed HTTP response is shown without rendering server-supplied HTML.
    }
  }

  const messages: Record<string, string> = {
    admin_user_outstanding_custody:
      "У пользователя осталось выданное оборудование. Сначала оформите возврат.",
    admin_user_active_procurement:
      "У пользователя есть незавершённая закупка. Завершите её или переназначьте ответственного.",
    admin_user_recovery_invariant:
      "Учётную запись владельца или резервного владельца сбрасывать нельзя.",
    admin_user_forbidden: "Недостаточно прав для сброса этой учётной записи.",
    admin_user_not_found: "Учётная запись уже сброшена или удалена. Обновите список.",
    admin_user_reset_identity_mismatch:
      "Данные пользователя изменились. Обновите список перед повторной попыткой.",
  };

  throw new Error(
    messages[code] ?? "Сброс не выполнен. Проверьте соединение и повторите попытку.",
  );
}

export function UserAccountReset({ user, currentUserId, canAssignAdmin }: Props) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");

  const mutation = useMutation({
    mutationFn: () => resetAccount(user),
    onSuccess: async () => {
      setOpen(false);
      setConfirmation("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });

  const allowed = user.id !== currentUserId
    && user.role !== "OWNER"
    && !user.is_recovery_identity
    && (user.role !== "ADMIN" || canAssignAdmin);

  if (!allowed) return null;

  const close = () => {
    if (mutation.isPending) return;
    setOpen(false);
    setConfirmation("");
    mutation.reset();
  };

  return (
    <div className="admin-user-reset">
      <div className="admin-user-reset__description">
        <strong>Сброс учётной записи</strong>
        <span>Отвязать Telegram и завершить сеансы. История складского учёта сохранится.</span>
      </div>
      <button
        className="button admin-user-reset__trigger"
        type="button"
        onClick={() => setOpen(true)}
      >
        Сбросить
      </button>

      {open ? (
        <div className="admin-user-reset__backdrop">
          <section
            className="admin-user-reset__dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={`reset-title-${user.id}`}
            onKeyDown={(event) => {
              if (event.key === "Escape") close();
            }}
          >
            <span className="admin-user-reset__eyebrow">Опасное действие</span>
            <h3 id={`reset-title-${user.id}`}>Сбросить учётную запись?</h3>
            <p className="admin-user-reset__identity">
              {user.first_name} {user.last_name ?? ""} · Telegram ID {user.telegram_user_id}
            </p>
            <p>
              Текущий доступ и все сеансы будут аннулированы. При следующем
              входе пользователь получит новую учётную запись и сможет снова
              отправить запрос доступа. История движения оборудования и
              журнал действий сохранятся.
            </p>
            <label htmlFor={`reset-confirm-${user.id}`}>
              Для подтверждения введите <strong>{CONFIRMATION}</strong>
              <input
                autoFocus
                id={`reset-confirm-${user.id}`}
                autoComplete="off"
                spellCheck={false}
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                disabled={mutation.isPending}
                maxLength={CONFIRMATION.length}
                placeholder={CONFIRMATION}
              />
            </label>
            {mutation.isError ? (
              <p className="admin-user-reset__error" role="alert">
                {mutation.error.message}
              </p>
            ) : null}
            <div className="admin-user-reset__dialog-actions">
              <button
                className="button button--ghost"
                type="button"
                onClick={close}
                disabled={mutation.isPending}
              >
                Отмена
              </button>
              <button
                className="button admin-user-reset__confirm"
                type="button"
                disabled={confirmation !== CONFIRMATION || mutation.isPending}
                onClick={() => mutation.mutate()}
              >
                {mutation.isPending ? "Сбрасываем…" : "Подтвердить сброс"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
