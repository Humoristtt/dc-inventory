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

import { useAuthState } from "../../features/auth/useAuthState";
import "../../features/admin/access-admin.css";
import {
  adminUserError,
  getAdminUsers,
  getUserAccessEvents,
  setAdminUserAccess,
  type AdminUser,
} from "../../shared/api/adminUsers";
import type {
  UserAccessStatus,
} from "../../shared/api/auth";
import { SpikatelBrand } from "../../shared/brand/SpikatelBrand";
import { TelegramFullscreenButton } from "../../shared/telegram/TelegramFullscreenButton";

const accessLabels: Record<UserAccessStatus, string> = {
  PENDING: "Ожидает подтверждения",
  APPROVED: "Доступ разрешён",
  REJECTED: "Запрос отклонён",
  BLOCKED: "Заблокирован",
};

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

  const admin = auth.data?.user.role === "ADMIN";

  const usersQuery = useQuery({
    queryKey: [
      "admin",
      "users",
      search,
      accessFilter,
    ],
    queryFn: ({ signal }) =>
      getAdminUsers(
        {
          query: search || undefined,
          accessStatus:
            accessFilter === "ALL"
              ? undefined
              : accessFilter,
        },
        signal,
      ),
    enabled: admin,
  });

  const historyQuery = useQuery({
    queryKey: [
      "admin",
      "user-access-events",
      historyUserId,
    ],
    queryFn: ({ signal }) => {
      if (historyUserId === null) {
        throw new Error("history user is not selected");
      }

      return getUserAccessEvents(historyUserId, signal);
    },
    enabled: admin && historyUserId !== null,
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

  if (auth.data === undefined) {
    return null;
  }

  if (!admin) {
    return <Navigate replace to="/more" />;
  }

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSearch(searchDraft.trim());
  };

  const changeAccess = (user: AdminUser) => {
    if (
      user.access_status !== "APPROVED"
      && user.access_status !== "BLOCKED"
    ) {
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

  return (
    <main className="admin-users-page">
      <header className="admin-users-page__header">
        <div className="more-page__toolbar">
          <SpikatelBrand inverse title="Инвентаризация ЦОД" />
          <TelegramFullscreenButton />
        </div>

        <div>
          <span className="more-page__kicker">Администрирование</span>
          <h1>Пользователи</h1>
        </div>
      </header>

      <div className="admin-users-page__body">
        <form
          className="admin-users__filters"
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
              onChange={(event) =>
                setAccessFilter(
                  event.target.value as
                    | UserAccessStatus
                    | "ALL",
                )
              }
            >
              <option value="ALL">Все</option>
              <option value="APPROVED">Доступ разрешён</option>
              <option value="BLOCKED">Заблокированы</option>
              <option value="PENDING">Ожидают подтверждения</option>
              <option value="REJECTED">Отклонены</option>
            </select>
          </label>

          <button
            className="admin-users__button"
            type="submit"
          >
            Найти
          </button>
        </form>

        {usersQuery.isError ? (
          <p role="alert">
            Не удалось загрузить пользователей.
            {" "}
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
            const mutable =
              user.access_status === "APPROVED"
              || user.access_status === "BLOCKED";

            const isCurrentUser =
              user.id === auth.data.user.id;

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
                  Роль:{" "}
                  {user.role === "ADMIN"
                    ? "Администратор"
                    : "Пользователь"}
                  {isCurrentUser
                    ? " · Текущая учётная запись"
                    : ""}
                </p>

                <div className="admin-user-card__actions">
                  {mutable && !isCurrentUser ? (
                    <button
                      className={
                        user.access_status === "APPROVED"
                          ? "admin-users__button admin-users__button--danger"
                          : "admin-users__button"
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
                    className="admin-users__button admin-users__button--secondary"
                    onClick={() =>
                      setHistoryUserId(
                        historyUserId === user.id
                          ? null
                          : user.id,
                      )
                    }
                    type="button"
                  >
                    {historyUserId === user.id
                      ? "Скрыть историю"
                      : "История доступа"}
                  </button>
                </div>

                {historyUserId === user.id ? (
                  <div className="admin-user-history">
                    {historyQuery.isFetching ? (
                      <p role="status">
                        Загружаем историю…
                      </p>
                    ) : null}

                    {historyQuery.isError ? (
                      <p role="alert">
                        Не удалось загрузить историю доступа.
                      </p>
                    ) : null}

                    {historyQuery.data?.items.length === 0 ? (
                      <p>Изменений доступа пока нет.</p>
                    ) : null}

                    {historyQuery.data?.items.map((event) => (
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
                          Кем: {event.actor_user_id}
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

        {accessMutation.isError ? (
          <p role="alert">
            {adminUserError(accessMutation.error)}
          </p>
        ) : null}
      </div>
    </main>
  );
}
