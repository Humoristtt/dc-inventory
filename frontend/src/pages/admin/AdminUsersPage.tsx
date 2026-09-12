import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  type FormEvent,
  useState,
} from "react";
import { Navigate } from "react-router-dom";

import "../../features/admin/access-admin.css";
import { useAuthState } from "../../features/auth/useAuthState";
import {
  adminUserError,
  decideAdminUserAccessRequest,
  getAdminUsers,
  getUserAccessEvents,
  getUserRoleEvents,
  setAdminUserAccess,
  setAdminUserRole,
  type AdminAccessRequestDecision,
  type AdminUser,
} from "../../shared/api/adminUsers";
import {
  hasCapability,
  ROLE_LABELS,
  type UserAccessStatus,
  type UserRole,
} from "../../shared/api/auth";
import { PageHeader } from "../../shared/ui";

const accessLabels: Record<UserAccessStatus, string> = {
  PENDING: "Ожидает подтверждения",
  APPROVED: "Доступ разрешён",
  REJECTED: "Запрос отклонён",
  BLOCKED: "Заблокирован",
};

const standardAssignableRoles: readonly UserRole[] = [
  "ENGINEER",
  "SENIOR_ENGINEER",
  "MANAGER",
];

const USERS_PAGE_SIZE = 50;
const HISTORY_PAGE_SIZE = 20;

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

function PaginationControls({
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
  const hasNext = offset + limit < total;

  if (!hasPrevious && !hasNext) {
    return null;
  }

  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);

  return (
    <div className="admin-pagination">
      <span>
        {label}: {start}–{end} из {total}
      </span>

      <div className="admin-pagination__actions">
        <button
          className="button button--ghost"
          disabled={!hasPrevious}
          onClick={onPrevious}
          type="button"
        >
          {previousLabel}
        </button>

        <button
          className="button button--ghost"
          disabled={!hasNext}
          onClick={onNext}
          type="button"
        >
          {nextLabel}
        </button>
      </div>
    </div>
  );
}

function displayName(user: AdminUser): string {
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

export function AdminUsersPage() {
  const auth = useAuthState();
  const queryClient = useQueryClient();

  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [accessFilter, setAccessFilter] = useState<
    UserAccessStatus | "ALL"
  >("ALL");
  const [historyUserId, setHistoryUserId] = useState<string | null>(
    null,
  );
  const [usersOffset, setUsersOffset] = useState(0);
  const [accessHistoryOffset, setAccessHistoryOffset] = useState(0);
  const [roleHistoryOffset, setRoleHistoryOffset] = useState(0);

  const currentUser = auth.data?.user;

  const canManageUsers = hasCapability(
    currentUser,
    "access.manage_users",
  );
  const canAssignStandardRoles = hasCapability(
    currentUser,
    "access.assign_standard_roles",
  );
  const canAssignAdmin = hasCapability(
    currentUser,
    "access.assign_admin",
  );

  const assignableRoles: readonly UserRole[] = canAssignAdmin
    ? [...standardAssignableRoles, "ADMIN"]
    : canAssignStandardRoles
      ? standardAssignableRoles
      : [];

  const usersQuery = useQuery({
    queryKey: [
      "admin",
      "users",
      search,
      accessFilter,
      usersOffset,
    ],
    queryFn: ({ signal }) =>
      getAdminUsers(
        {
          query: search || undefined,
          accessStatus:
            accessFilter === "ALL"
              ? undefined
              : accessFilter,
          limit: USERS_PAGE_SIZE,
          offset: usersOffset,
        },
        signal,
      ),
    enabled: canManageUsers,
  });

  const accessHistoryQuery = useQuery({
    queryKey: [
      "admin",
      "user-access-events",
      historyUserId,
      accessHistoryOffset,
    ],
    queryFn: ({ signal }) => {
      if (historyUserId === null) {
        throw new Error("history user is not selected");
      }

      return getUserAccessEvents(
        historyUserId,
        {
          limit: HISTORY_PAGE_SIZE,
          offset: accessHistoryOffset,
        },
        signal,
      );
    },
    enabled: canManageUsers && historyUserId !== null,
  });

  const roleHistoryQuery = useQuery({
    queryKey: [
      "admin",
      "user-role-events",
      historyUserId,
      roleHistoryOffset,
    ],
    queryFn: ({ signal }) => {
      if (historyUserId === null) {
        throw new Error("history user is not selected");
      }

      return getUserRoleEvents(
        historyUserId,
        {
          limit: HISTORY_PAGE_SIZE,
          offset: roleHistoryOffset,
        },
        signal,
      );
    },
    enabled: canManageUsers && historyUserId !== null,
  });

  const accessMutation = useMutation({
    mutationFn: ({
      userId,
      accessStatus,
    }: {
      userId: string;
      accessStatus: UserAccessStatus;
    }) => setAdminUserAccess(userId, accessStatus),

    onSuccess: async (_, variables) => {
      await queryClient.invalidateQueries({
        queryKey: ["admin", "users"],
      });

      await queryClient.invalidateQueries({
        queryKey: [
          "admin",
          "user-access-events",
          variables.userId,
        ],
      });
    },
  });

  const accessDecisionMutation = useMutation({
    mutationFn: ({
      userId,
      decision,
    }: {
      userId: string;
      decision: AdminAccessRequestDecision;
    }) =>
      decideAdminUserAccessRequest(
        userId,
        decision,
      ),

    onSuccess: async (_, variables) => {
      await queryClient.invalidateQueries({
        queryKey: ["admin", "users"],
      });

      await queryClient.invalidateQueries({
        queryKey: [
          "admin",
          "user-access-events",
          variables.userId,
        ],
      });
    },
  });

  const roleMutation = useMutation({
    mutationFn: ({
      userId,
      role,
    }: {
      userId: string;
      role: UserRole;
    }) => setAdminUserRole(userId, role),

    onSuccess: async (_, variables) => {
      await queryClient.invalidateQueries({
        queryKey: ["admin", "users"],
      });

      await queryClient.invalidateQueries({
        queryKey: [
          "admin",
          "user-role-events",
          variables.userId,
        ],
      });
    },
  });

  if (auth.data === undefined) {
    return null;
  }

  if (!canManageUsers) {
    return <Navigate replace to="/more" />;
  }

  const resetHistory = () => {
    setHistoryUserId(null);
    setAccessHistoryOffset(0);
    setRoleHistoryOffset(0);
  };

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSearch(searchDraft.trim());
    setUsersOffset(0);
    resetHistory();
  };

  const changeUsersPage = (nextOffset: number) => {
    setUsersOffset(Math.max(0, nextOffset));
    resetHistory();
  };

  const toggleHistory = (userId: string) => {
    setAccessHistoryOffset(0);
    setRoleHistoryOffset(0);
    setHistoryUserId((current) =>
      current === userId ? null : userId
    );
  };

  const canDecidePendingAccess = (
    user: AdminUser,
  ): boolean => {
    if (
      user.access_status !== "PENDING"
      || user.id === currentUser?.id
      || user.role === "OWNER"
    ) {
      return false;
    }

    if (
      user.role === "ADMIN"
      && !canAssignAdmin
    ) {
      return false;
    }

    return true;
  };

  const canManageTargetAccess = (user: AdminUser): boolean => {
    if (user.id === currentUser?.id || user.role === "OWNER") {
      return false;
    }

    if (user.role === "ADMIN" && !canAssignAdmin) {
      return false;
    }

    return (
      user.access_status === "APPROVED"
      || user.access_status === "BLOCKED"
    );
  };

  const canManageTargetRole = (user: AdminUser): boolean => {
    if (
      user.id === currentUser?.id
      || user.role === "OWNER"
      || assignableRoles.length === 0
    ) {
      return false;
    }

    if (user.role === "ADMIN" && !canAssignAdmin) {
      return false;
    }

    return true;
  };

  const decidePendingAccess = (
    user: AdminUser,
    decision: AdminAccessRequestDecision,
  ) => {
    if (!canDecidePendingAccess(user)) {
      return;
    }

    if (
      decision === "REJECT"
      && !window.confirm(
        `Отклонить запрос доступа для ${displayName(user)}?`,
      )
    ) {
      return;
    }

    accessDecisionMutation.mutate({
      userId: user.id,
      decision,
    });
  };

  const changeAccess = (user: AdminUser) => {
    if (!canManageTargetAccess(user)) {
      return;
    }

    const nextStatus: UserAccessStatus =
      user.access_status === "APPROVED"
        ? "BLOCKED"
        : "APPROVED";

    if (
      nextStatus === "BLOCKED"
      && !window.confirm(
        `Заблокировать доступ для ${displayName(user)}? Активные сессии будут завершены.`,
      )
    ) {
      return;
    }

    accessMutation.mutate({
      userId: user.id,
      accessStatus: nextStatus,
    });
  };

  const changeRole = (
    user: AdminUser,
    nextRole: UserRole,
  ) => {
    if (
      !canManageTargetRole(user)
      || nextRole === user.role
      || !assignableRoles.includes(nextRole)
    ) {
      return;
    }

    if (
      !window.confirm(
        `Изменить роль для ${displayName(user)}: ${ROLE_LABELS[user.role]} → ${ROLE_LABELS[nextRole]}?`,
      )
    ) {
      return;
    }

    roleMutation.mutate({
      userId: user.id,
      role: nextRole,
    });
  };

  return (
    <main className="admin-users-page">
      <PageHeader
        kicker="Администрирование"
        title="Пользователи"
      />

      <div className="admin-users-page__body">
        <form
          className="admin-users__filters form-surface"
          onSubmit={submitSearch}
        >
          <label>
            Поиск
            <input
              maxLength={100}
              placeholder="Имя, username или Telegram ID"
              value={searchDraft}
              onChange={(event) =>
                setSearchDraft(event.target.value)
              }
            />
          </label>

          <label>
            Статус
            <select
              value={accessFilter}
              onChange={(event) => {
                setAccessFilter(
                  event.target.value as
                    | UserAccessStatus
                    | "ALL",
                );
                setUsersOffset(0);
                resetHistory();
              }}
            >
              <option value="ALL">Все</option>
              <option value="APPROVED">Доступ разрешён</option>
              <option value="BLOCKED">Заблокированы</option>
              <option value="PENDING">Ожидают подтверждения</option>
              <option value="REJECTED">Отклонены</option>
            </select>
          </label>

          <button
            className="button button--dark"
            type="submit"
          >
            Найти
          </button>
        </form>

        {usersQuery.isError ? (
          <p role="alert">
            Не удалось загрузить пользователей.{" "}
            <button
              type="button"
              onClick={() => void usersQuery.refetch()}
            >
              Повторить
            </button>
          </p>
        ) : null}

        {usersQuery.isPending ? (
          <p role="status">Загружаем пользователей…</p>
        ) : null}

        <div className="admin-users__list">
          {usersQuery.data?.items.map((user) => {
            const isCurrentUser =
              user.id === currentUser?.id;
            const roleMutable =
              canManageTargetRole(user);
            const accessMutable =
              canManageTargetAccess(user);
            const pendingDecisionMutable =
              canDecidePendingAccess(user);

            return (
              <section
                className="admin-user-card"
                key={user.id}
              >
                <div className="admin-user-card__heading">
                  <div>
                    <h2>{displayName(user)}</h2>
                    <p>Telegram ID: {user.telegram_user_id}</p>
                  </div>

                  <span
                    className={`admin-user-card__status admin-user-card__status--${user.access_status.toLowerCase()}`}
                  >
                    {accessLabels[user.access_status]}
                  </span>
                </div>

                <p className="admin-user-card__meta">
                  Роль: {ROLE_LABELS[user.role]}
                  {user.is_recovery_identity
                    ? " · Recovery OWNER"
                    : ""}
                  {isCurrentUser
                    ? " · Текущая учётная запись"
                    : ""}
                </p>

                {roleMutable ? (
                  <label>
                    Роль пользователя
                    <select
                      disabled={roleMutation.isPending}
                      value={user.role}
                      onChange={(event) =>
                        changeRole(
                          user,
                          event.target.value as UserRole,
                        )
                      }
                    >
                      {assignableRoles.map((role) => (
                        <option
                          key={role}
                          value={role}
                        >
                          {ROLE_LABELS[role]}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}

                <div className="admin-user-card__actions">
                  {pendingDecisionMutable ? (
                    <>
                      <button
                        className="button button--dark"
                        disabled={
                          accessDecisionMutation.isPending
                        }
                        onClick={() =>
                          decidePendingAccess(
                            user,
                            "APPROVE",
                          )
                        }
                        type="button"
                      >
                        Разрешить
                      </button>

                      <button
                        className="button button--danger"
                        disabled={
                          accessDecisionMutation.isPending
                        }
                        onClick={() =>
                          decidePendingAccess(
                            user,
                            "REJECT",
                          )
                        }
                        type="button"
                      >
                        Отклонить
                      </button>
                    </>
                  ) : null}

                  {accessMutable ? (
                    <button
                      className={
                        user.access_status === "APPROVED"
                          ? "button button--danger"
                          : "button button--dark"
                      }
                      disabled={accessMutation.isPending}
                      onClick={() => changeAccess(user)}
                      type="button"
                    >
                      {user.access_status === "APPROVED"
                        ? "Заблокировать"
                        : "Разблокировать"}
                    </button>
                  ) : null}

                  <button
                    className="button button--ghost"
                    onClick={() =>
                      toggleHistory(user.id)
                    }
                    type="button"
                  >
                    {historyUserId === user.id
                      ? "Скрыть историю"
                      : "История изменений"}
                  </button>
                </div>

                {historyUserId === user.id ? (
                  <div className="admin-user-history">
                    {accessHistoryQuery.isFetching
                    || roleHistoryQuery.isFetching ? (
                      <p role="status">
                        Загружаем историю…
                      </p>
                    ) : null}

                    {accessHistoryQuery.isError ? (
                      <p role="alert">
                        Не удалось загрузить историю доступа.
                      </p>
                    ) : null}

                    {roleHistoryQuery.isError ? (
                      <p role="alert">
                        Не удалось загрузить историю ролей.
                      </p>
                    ) : null}

                    <h3>Роли</h3>

                    <PaginationControls
                      label="Роли"
                      limit={HISTORY_PAGE_SIZE}
                      nextLabel="Следующая страница ролей"
                      offset={roleHistoryOffset}
                      onNext={() =>
                        setRoleHistoryOffset(
                          roleHistoryOffset + HISTORY_PAGE_SIZE,
                        )
                      }
                      onPrevious={() =>
                        setRoleHistoryOffset(
                          Math.max(
                            0,
                            roleHistoryOffset - HISTORY_PAGE_SIZE,
                          ),
                        )
                      }
                      previousLabel="Предыдущая страница ролей"
                      total={roleHistoryQuery.data?.total ?? 0}
                    />

                    {roleHistoryQuery.data?.items.length === 0 ? (
                      <p>Изменений роли пока нет.</p>
                    ) : null}

                    {roleHistoryQuery.data?.items.map((event) => (
                      <div
                        className="admin-user-history__event"
                        key={event.id}
                      >
                        <strong>
                          {ROLE_LABELS[event.before_role]}
                          {" → "}
                          {ROLE_LABELS[event.after_role]}
                        </strong>
                        <span>
                          Кем: {event.actor_display_name}
                        </span>
                        <span>
                          {new Date(
                            event.occurred_at,
                          ).toLocaleString("ru-RU")}
                        </span>
                      </div>
                    ))}

                    <h3>Доступ</h3>

                    <PaginationControls
                      label="Доступ"
                      limit={HISTORY_PAGE_SIZE}
                      nextLabel="Следующая страница доступа"
                      offset={accessHistoryOffset}
                      onNext={() =>
                        setAccessHistoryOffset(
                          accessHistoryOffset + HISTORY_PAGE_SIZE,
                        )
                      }
                      onPrevious={() =>
                        setAccessHistoryOffset(
                          Math.max(
                            0,
                            accessHistoryOffset - HISTORY_PAGE_SIZE,
                          ),
                        )
                      }
                      previousLabel="Предыдущая страница доступа"
                      total={accessHistoryQuery.data?.total ?? 0}
                    />

                    {accessHistoryQuery.data?.items.length === 0 ? (
                      <p>Изменений доступа пока нет.</p>
                    ) : null}

                    {accessHistoryQuery.data?.items.map((event) => (
                      <div
                        className="admin-user-history__event"
                        key={event.id}
                      >
                        <strong>
                          {accessLabels[event.before_access_status]}
                          {" → "}
                          {accessLabels[event.after_access_status]}
                        </strong>
                        <span>
                          Кем: {event.actor_display_name}
                        </span>
                        <span>
                          {new Date(
                            event.occurred_at,
                          ).toLocaleString("ru-RU")}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </section>
            );
          })}
        </div>

        <PaginationControls
          label="Пользователи"
          limit={USERS_PAGE_SIZE}
          nextLabel="Следующая страница"
          offset={usersOffset}
          onNext={() =>
            changeUsersPage(
              usersOffset + USERS_PAGE_SIZE,
            )
          }
          onPrevious={() =>
            changeUsersPage(
              usersOffset - USERS_PAGE_SIZE,
            )
          }
          previousLabel="Предыдущая страница"
          total={usersQuery.data?.total ?? 0}
        />

        {accessMutation.isError ? (
          <p role="alert">
            {adminUserError(accessMutation.error)}
          </p>
        ) : null}

        {accessDecisionMutation.isError ? (
          <p role="alert">
            {adminUserError(
              accessDecisionMutation.error,
            )}
          </p>
        ) : null}

        {roleMutation.isError ? (
          <p role="alert">
            {adminUserError(roleMutation.error)}
          </p>
        ) : null}
      </div>
    </main>
  );
}
