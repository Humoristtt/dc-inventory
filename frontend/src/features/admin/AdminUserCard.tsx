import {
  Button,
  Select,
} from "../../shared/ui";
import {
  ROLE_LABELS,
  type UserRole,
} from "../../shared/api/auth";
import type {
  AdminAccessRequestDecision,
  AdminUser,
} from "../../shared/api/adminUsers";
import {
  ACCESS_LABELS,
  displayAdminUserName,
} from "./adminUserPresentation";
import {
  AdminUserHistory,
  type AdminUserHistoryProps,
} from "./AdminUserHistory";
import {
  UserAccountReset,
} from "./UserAccountReset";

type AdminUserCardProps = {
  accessMutationPending: boolean;
  accessDecisionPending: boolean;
  assignableRoles:
    readonly UserRole[];
  canAssignAdmin: boolean;
  currentUserId:
    | string
    | undefined;
  historyOpen: boolean;
  history:
    | AdminUserHistoryProps
    | undefined;
  pendingDecisionMutable: boolean;
  accessMutable: boolean;
  roleMutable: boolean;
  roleMutationPending: boolean;
  user: AdminUser;
  onAccessChange: (
    user: AdminUser,
  ) => void;
  onDecision: (
    user: AdminUser,
    decision:
      AdminAccessRequestDecision,
  ) => void;
  onRoleChange: (
    user: AdminUser,
    role: UserRole,
  ) => void;
  onToggleHistory: (
    userId: string,
  ) => void;
};

export function AdminUserCard({
  accessMutationPending,
  accessDecisionPending,
  assignableRoles,
  canAssignAdmin,
  currentUserId,
  historyOpen,
  history,
  pendingDecisionMutable,
  accessMutable,
  roleMutable,
  roleMutationPending,
  user,
  onAccessChange,
  onDecision,
  onRoleChange,
  onToggleHistory,
}: AdminUserCardProps) {
  const isCurrentUser =
    user.id === currentUserId;

  return (
    <section className="admin-user-card">
      <div className="admin-user-card__heading">
        <div>
          <h2>
            {displayAdminUserName(user)}
          </h2>
          <p>
            Telegram ID: {
              user.telegram_user_id
            }
          </p>
        </div>

        <span
          className={
            `admin-user-card__status admin-user-card__status--${user.access_status.toLowerCase()}`
          }
        >
          {ACCESS_LABELS[user.access_status]}
        </span>
      </div>

      <p className="admin-user-card__meta">
        Роль: {ROLE_LABELS[user.role]}
        {
          user.is_recovery_identity
            ? " · Recovery OWNER"
            : ""
        }
        {
          isCurrentUser
            ? " · Текущая учётная запись"
            : ""
        }
      </p>

      {roleMutable ? (
        <label>
          Роль пользователя
          <Select
            disabled={roleMutationPending}
            onChange={(event) =>
              onRoleChange(
                user,
                event.target.value as UserRole,
              )
            }
            value={user.role}
          >
            {assignableRoles.map((role) => (
              <option
                key={role}
                value={role}
              >
                {ROLE_LABELS[role]}
              </option>
            ))}
          </Select>
        </label>
      ) : null}

      <div className="admin-user-card__actions">
        {pendingDecisionMutable ? (
          <>
            <Button
              className="button button--dark"
              disabled={accessDecisionPending}
              onClick={() =>
                onDecision(
                  user,
                  "APPROVE",
                )
              }
            >
              Разрешить
            </Button>

            <Button
              className="button button--danger"
              disabled={accessDecisionPending}
              onClick={() =>
                onDecision(
                  user,
                  "REJECT",
                )
              }
            >
              Отклонить
            </Button>
          </>
        ) : null}

        {accessMutable ? (
          <Button
            className={
              user.access_status === "APPROVED"
                ? "button button--danger"
                : "button button--dark"
            }
            disabled={accessMutationPending}
            onClick={() =>
              onAccessChange(user)
            }
          >
            {
              user.access_status === "APPROVED"
                ? "Заблокировать"
                : "Разблокировать"
            }
          </Button>
        ) : null}

        <Button
          className="button button--ghost"
          onClick={() =>
            onToggleHistory(user.id)
          }
        >
          {
            historyOpen
              ? "Скрыть историю"
              : "История изменений"
          }
        </Button>
      </div>

      <UserAccountReset
        canAssignAdmin={canAssignAdmin}
        currentUserId={currentUserId}
        user={user}
      />

      {historyOpen && history ? (
        <AdminUserHistory {...history} />
      ) : null}
    </section>
  );
}
