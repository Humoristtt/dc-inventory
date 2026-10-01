import {
  type FormEvent,
} from "react";

import {
  Button,
  Input,
  Select,
} from "../../shared/ui";
import { UserAccountReset } from "./UserAccountReset";
import type {
  AdminAccessRequestDecision,
  AdminUser,
  UserAccessEventPage,
  UserRoleEventPage,
} from "../../shared/api/adminUsers";
import {
  ROLE_LABELS,
  type UserAccessStatus,
  type UserRole,
} from "../../shared/api/auth";

export const ACCESS_LABELS:
  Record<UserAccessStatus, string> = {
    PENDING: "Ожидает подтверждения",
    APPROVED: "Доступ разрешён",
    REJECTED: "Запрос отклонён",
    BLOCKED: "Заблокирован",
  };

export const STANDARD_ASSIGNABLE_ROLES:
  readonly UserRole[] = [
    "ENGINEER",
    "SENIOR_ENGINEER",
    "MANAGER",
  ];

export const USERS_PAGE_SIZE = 50;
export const HISTORY_PAGE_SIZE = 20;

export function displayAdminUserName(
  user: AdminUser,
): string {
  const fullName = [
    user.first_name,
    user.last_name,
  ]
    .filter(Boolean)
    .join(" ");

  if (user.username) {
    return `${fullName} · @${user.username}`;
  }

  return fullName;
}

type PaginationControlsProps = {
  label: string;
  offset: number;
  limit: number;
  total: number;
  previousLabel: string;
  nextLabel: string;
  onPrevious: () => void;
  onNext: () => void;
};

export function PaginationControls({
  label,
  offset,
  limit,
  total,
  previousLabel,
  nextLabel,
  onPrevious,
  onNext,
}: PaginationControlsProps) {
  const hasPrevious = offset > 0;
  const hasNext =
    offset + limit < total;

  if (!hasPrevious && !hasNext) {
    return null;
  }

  const start =
    total === 0
      ? 0
      : offset + 1;
  const end = Math.min(
    offset + limit,
    total,
  );

  return (
    <div className="admin-pagination">
      <span>
        {label}: {start}–{end} из {total}
      </span>

      <div className="admin-pagination__actions">
        <Button
          className="button button--ghost"
          disabled={!hasPrevious}
          onClick={onPrevious}
        >
          {previousLabel}
        </Button>

        <Button
          className="button button--ghost"
          disabled={!hasNext}
          onClick={onNext}
        >
          {nextLabel}
        </Button>
      </div>
    </div>
  );
}

type AdminUserFiltersProps = {
  accessFilter:
    | UserAccessStatus
    | "ALL";
  searchDraft: string;
  onAccessFilterChange: (
    value:
      | UserAccessStatus
      | "ALL",
  ) => void;
  onSearchDraftChange: (
    value: string,
  ) => void;
  onSubmit: (
    event:
      FormEvent<HTMLFormElement>,
  ) => void;
};

export function AdminUserFilters({
  accessFilter,
  searchDraft,
  onAccessFilterChange,
  onSearchDraftChange,
  onSubmit,
}: AdminUserFiltersProps) {
  return (
    <form
      className="admin-users__filters form-surface"
      onSubmit={onSubmit}
    >
      <label>
        Поиск
        <Input
          data-gramm="false"
          data-gramm_editor="false"
          maxLength={100}
          onChange={(event) =>
            onSearchDraftChange(
              event.target.value,
            )
          }
          placeholder="Имя, username или Telegram ID"
          value={searchDraft}
        />
      </label>

      <label>
        Статус
        <Select
          onChange={(event) =>
            onAccessFilterChange(
              event.target.value as
                | UserAccessStatus
                | "ALL",
            )
          }
          value={accessFilter}
        >
          <option value="ALL">
            Все
          </option>
          <option value="APPROVED">
            Доступ разрешён
          </option>
          <option value="BLOCKED">
            Заблокированы
          </option>
          <option value="PENDING">
            Ожидают подтверждения
          </option>
          <option value="REJECTED">
            Отклонены
          </option>
        </Select>
      </label>

      <Button
        className="button button--dark"
        type="submit"
      >
        Найти
      </Button>
    </form>
  );
}

type AdminUserHistoryProps = {
  accessData:
    | UserAccessEventPage
    | undefined;
  accessError: boolean;
  accessFetching: boolean;
  accessOffset: number;
  roleData:
    | UserRoleEventPage
    | undefined;
  roleError: boolean;
  roleFetching: boolean;
  roleOffset: number;
  onAccessOffsetChange: (
    offset: number,
  ) => void;
  onRoleOffsetChange: (
    offset: number,
  ) => void;
};

export function AdminUserHistory({
  accessData,
  accessError,
  accessFetching,
  accessOffset,
  roleData,
  roleError,
  roleFetching,
  roleOffset,
  onAccessOffsetChange,
  onRoleOffsetChange,
}: AdminUserHistoryProps) {
  return (
    <div className="admin-user-history">
      {accessFetching
      || roleFetching ? (
        <p role="status">
          Загружаем историю…
        </p>
      ) : null}

      {accessError ? (
        <p role="alert">
          Не удалось загрузить
          историю доступа.
        </p>
      ) : null}

      {roleError ? (
        <p role="alert">
          Не удалось загрузить
          историю ролей.
        </p>
      ) : null}

      <h3>Роли</h3>

      <PaginationControls
        label="Роли"
        limit={HISTORY_PAGE_SIZE}
        nextLabel="Следующая страница ролей"
        offset={roleOffset}
        onNext={() =>
          onRoleOffsetChange(
            roleOffset
            + HISTORY_PAGE_SIZE,
          )
        }
        onPrevious={() =>
          onRoleOffsetChange(
            Math.max(
              0,
              roleOffset
              - HISTORY_PAGE_SIZE,
            ),
          )
        }
        previousLabel="Предыдущая страница ролей"
        total={
          roleData?.total ?? 0
        }
      />

      {roleData?.items.length === 0 ? (
        <p>
          Изменений роли пока нет.
        </p>
      ) : null}

      {roleData?.items.map(
        (event) => (
          <div
            className="admin-user-history__event"
            key={event.id}
          >
            <strong>
              {
                ROLE_LABELS[
                  event.before_role
                ]
              }
              {" → "}
              {
                ROLE_LABELS[
                  event.after_role
                ]
              }
            </strong>
            <span>
              Кем: {
                event.actor_display_name
              }
            </span>
            <span>
              {
                new Date(
                  event.occurred_at,
                ).toLocaleString(
                  "ru-RU",
                )
              }
            </span>
          </div>
        ),
      )}

      <h3>Доступ</h3>

      <PaginationControls
        label="Доступ"
        limit={HISTORY_PAGE_SIZE}
        nextLabel="Следующая страница доступа"
        offset={accessOffset}
        onNext={() =>
          onAccessOffsetChange(
            accessOffset
            + HISTORY_PAGE_SIZE,
          )
        }
        onPrevious={() =>
          onAccessOffsetChange(
            Math.max(
              0,
              accessOffset
              - HISTORY_PAGE_SIZE,
            ),
          )
        }
        previousLabel="Предыдущая страница доступа"
        total={
          accessData?.total ?? 0
        }
      />

      {accessData?.items.length
      === 0 ? (
        <p>
          Изменений доступа пока нет.
        </p>
      ) : null}

      {accessData?.items.map(
        (event) => (
          <div
            className="admin-user-history__event"
            key={event.id}
          >
            <strong>
              {
                ACCESS_LABELS[
                  event.before_access_status
                ]
              }
              {" → "}
              {
                ACCESS_LABELS[
                  event.after_access_status
                ]
              }
            </strong>
            <span>
              Кем: {
                event.actor_display_name
              }
            </span>
            <span>
              {
                new Date(
                  event.occurred_at,
                ).toLocaleString(
                  "ru-RU",
                )
              }
            </span>
          </div>
        ),
      )}
    </div>
  );
}

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
    <section
      className="admin-user-card"
      key={user.id}
    >
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
          {
            ACCESS_LABELS[
              user.access_status
            ]
          }
        </span>
      </div>

      <p className="admin-user-card__meta">
        Роль: {
          ROLE_LABELS[user.role]
        }
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
            disabled={
              roleMutationPending
            }
            onChange={(event) =>
              onRoleChange(
                user,
                event.target
                  .value as UserRole,
              )
            }
            value={user.role}
          >
            {assignableRoles.map(
              (role) => (
                <option
                  key={role}
                  value={role}
                >
                  {ROLE_LABELS[role]}
                </option>
              ),
            )}
          </Select>
        </label>
      ) : null}

      <div className="admin-user-card__actions">
        {pendingDecisionMutable ? (
          <>
            <Button
              className="button button--dark"
              disabled={
                accessDecisionPending
              }
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
              disabled={
                accessDecisionPending
              }
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
              user.access_status
              === "APPROVED"
                ? "button button--danger"
                : "button button--dark"
            }
            disabled={
              accessMutationPending
            }
            onClick={() =>
              onAccessChange(user)
            }
          >
            {
              user.access_status
              === "APPROVED"
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
        canAssignAdmin={
          canAssignAdmin
        }
        currentUserId={
          currentUserId
        }
        user={user}
      />

      {historyOpen && history ? (
        <AdminUserHistory
          {...history}
        />
      ) : null}
    </section>
  );
}
