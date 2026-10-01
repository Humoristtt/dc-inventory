import { Button } from "../../shared/ui";
import {
  useQuery,
} from "@tanstack/react-query";
import {
  type FormEvent,
  useState,
} from "react";
import { Navigate } from "react-router-dom";

import "../../features/admin/access-admin.css";
import {
  AdminUserCard,
} from "../../features/admin/AdminUserCard";
import {
  AdminUserFilters,
} from "../../features/admin/AdminUserFilters";
import {
  PaginationControls,
} from "../../features/admin/AdminPagination";
import {
  HISTORY_PAGE_SIZE,
  STANDARD_ASSIGNABLE_ROLES,
  USERS_PAGE_SIZE,
  displayAdminUserName,
} from "../../features/admin/adminUserPresentation";
import {
  canDecidePendingAccess,
  canManageTargetAccess,
  canManageTargetRole,
} from "../../features/admin/adminUserPolicy";
import {
  useAdminUserMutations,
} from "../../features/admin/useAdminUserMutations";
import { useAuthState } from "../../features/auth/useAuthState";
import {
  adminUserError,
  getAdminUsers,
  getUserAccessEvents,
  getUserRoleEvents,
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

export function AdminUsersPage() {
  const auth = useAuthState();

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

  const assignableRoles: readonly UserRole[] =
    canAssignAdmin
      ? [
          ...STANDARD_ASSIGNABLE_ROLES,
          "ADMIN",
        ]
      : canAssignStandardRoles
        ? STANDARD_ASSIGNABLE_ROLES
        : [];

  const targetPolicy = {
    currentUserId:
      currentUser?.id,
    canAssignAdmin,
    assignableRoles,
  } as const;

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

  const {
    accessDecisionMutation,
    accessMutation,
    roleMutation,
  } = useAdminUserMutations();

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

  const decidePendingAccess = (
    user: AdminUser,
    decision: AdminAccessRequestDecision,
  ) => {
    if (!canDecidePendingAccess(user, targetPolicy)) {
      return;
    }

    if (
      decision === "REJECT"
      && !window.confirm(
        `Отклонить запрос доступа для ${displayAdminUserName(user)}?`,
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
    if (!canManageTargetAccess(user, targetPolicy)) {
      return;
    }

    const nextStatus: UserAccessStatus =
      user.access_status === "APPROVED"
        ? "BLOCKED"
        : "APPROVED";

    if (
      nextStatus === "BLOCKED"
      && !window.confirm(
        `Заблокировать доступ для ${displayAdminUserName(user)}? Активные сессии будут завершены.`,
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
      !canManageTargetRole(user, targetPolicy)
      || nextRole === user.role
      || !assignableRoles.includes(nextRole)
    ) {
      return;
    }

    if (
      !window.confirm(
        `Изменить роль для ${displayAdminUserName(user)}: ${ROLE_LABELS[user.role]} → ${ROLE_LABELS[nextRole]}?`,
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
        <AdminUserFilters
          accessFilter={accessFilter}
          onAccessFilterChange={(value) => {
            setAccessFilter(value);
            setUsersOffset(0);
            resetHistory();
          }}
          onSearchDraftChange={
            setSearchDraft
          }
          onSubmit={submitSearch}
          searchDraft={searchDraft}
        />

        {usersQuery.isError ? (
          <p role="alert">
            Не удалось загрузить пользователей.{" "}
            <Button
              type="button"
              onClick={() => void usersQuery.refetch()}
            >
              Повторить
            </Button>
          </p>
        ) : null}

        {usersQuery.isPending ? (
          <p role="status">Загружаем пользователей…</p>
        ) : null}

        <div className="admin-users__list">
          {usersQuery.data?.items.map(
            (user) => {
              const roleMutable =
                canManageTargetRole(user, targetPolicy);
              const accessMutable =
                canManageTargetAccess(
                  user,
                );
              const pendingDecisionMutable =
                canDecidePendingAccess(
                  user,
                );
              const historyOpen =
                historyUserId === user.id;

              return (
                <AdminUserCard
                  accessDecisionPending={
                    accessDecisionMutation.isPending
                  }
                  accessMutable={
                    accessMutable
                  }
                  accessMutationPending={
                    accessMutation.isPending
                  }
                  assignableRoles={
                    assignableRoles
                  }
                  canAssignAdmin={
                    canAssignAdmin
                  }
                  currentUserId={
                    currentUser?.id
                  }
                  history={
                    historyOpen
                      ? {
                          accessData:
                            accessHistoryQuery.data,
                          accessError:
                            accessHistoryQuery.isError,
                          accessFetching:
                            accessHistoryQuery.isFetching,
                          accessOffset:
                            accessHistoryOffset,
                          onAccessOffsetChange:
                            setAccessHistoryOffset,
                          onRoleOffsetChange:
                            setRoleHistoryOffset,
                          roleData:
                            roleHistoryQuery.data,
                          roleError:
                            roleHistoryQuery.isError,
                          roleFetching:
                            roleHistoryQuery.isFetching,
                          roleOffset:
                            roleHistoryOffset,
                        }
                      : undefined
                  }
                  historyOpen={
                    historyOpen
                  }
                  key={user.id}
                  onAccessChange={
                    changeAccess
                  }
                  onDecision={
                    decidePendingAccess
                  }
                  onRoleChange={
                    changeRole
                  }
                  onToggleHistory={
                    toggleHistory
                  }
                  pendingDecisionMutable={
                    pendingDecisionMutable
                  }
                  roleMutable={
                    roleMutable
                  }
                  roleMutationPending={
                    roleMutation.isPending
                  }
                  user={user}
                />
              );
            },
          )}
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
