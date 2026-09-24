import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  type AdminUser,
  resetAdminUserAccount,
  resetAdminUserError,
} from "../../shared/api/adminUsers";
import "./user-account-reset.css";

const CONFIRMATION = "СБРОСИТЬ";

type Props = {
  user: AdminUser;
  currentUserId: string | undefined;
  canAssignAdmin: boolean;
};

export function UserAccountReset({ user, currentUserId, canAssignAdmin }: Props) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      resetAdminUserAccount(
        user.id,
        user.telegram_user_id,
        CONFIRMATION,
      ),
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
                {resetAdminUserError(mutation.error)}
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
