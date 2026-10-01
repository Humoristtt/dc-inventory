import type {
  FormEvent,
} from "react";

import {
  Button,
  Input,
  Select,
} from "../../shared/ui";
import type {
  UserAccessStatus,
} from "../../shared/api/auth";

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
          <option value="ALL">Все</option>
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
