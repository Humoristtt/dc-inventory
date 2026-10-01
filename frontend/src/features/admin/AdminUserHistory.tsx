import {
  ROLE_LABELS,
} from "../../shared/api/auth";
import type {
  UserAccessEventPage,
  UserRoleEventPage,
} from "../../shared/api/adminUsers";
import {
  ACCESS_LABELS,
  HISTORY_PAGE_SIZE,
} from "./adminUserPresentation";
import {
  PaginationControls,
} from "./AdminPagination";

export type AdminUserHistoryProps = {
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
      {accessFetching || roleFetching ? (
        <p role="status">
          Загружаем историю…
        </p>
      ) : null}

      {accessError ? (
        <p role="alert">
          Не удалось загрузить историю доступа.
        </p>
      ) : null}

      {roleError ? (
        <p role="alert">
          Не удалось загрузить историю ролей.
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
        total={roleData?.total ?? 0}
      />

      {roleData?.items.length === 0 ? (
        <p>Изменений роли пока нет.</p>
      ) : null}

      {roleData?.items.map((event) => (
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
        total={accessData?.total ?? 0}
      />

      {accessData?.items.length === 0 ? (
        <p>Изменений доступа пока нет.</p>
      ) : null}

      {accessData?.items.map((event) => (
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
  );
}
