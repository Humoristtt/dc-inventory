import {
  Button,
  Input,
  Select,
} from "../../shared/ui";
import type {
  ProcurementRequest,
  UserSummary,
} from "../../shared/api/procurement";
import {
  ProcurementDialog,
} from "./ProcurementDialog";
import type {
  ProcurementAction,
} from "./procurementDetailDialogTypes";

export function ProcurementManagerDialog({
  current,
  managerId,
  managerOptions,
  managerSearch,
  managersError,
  managersHasNextPage,
  managersLoading,
  managersLoadingNext,
  mutationPending,
  open,
  onAction,
  onClose,
  onFetchMore,
  onManagerChange,
  onManagerSearchChange,
  onRetry,
}: {
  current: ProcurementRequest;
  managerId: string;
  managerOptions:
    readonly UserSummary[];
  managerSearch: string;
  managersError: boolean;
  managersHasNextPage: boolean;
  managersLoading: boolean;
  managersLoadingNext: boolean;
  mutationPending: boolean;
  open: boolean;
  onAction: ProcurementAction;
  onClose: () => void;
  onFetchMore: () => void;
  onManagerChange:
    (value: string) => void;
  onManagerSearchChange:
    (value: string) => void;
  onRetry: () => void;
}) {
  return (
    <ProcurementDialog
      onClose={onClose}
      open={open}
      title="Передать менеджеру"
    >
      <label>
        Поиск менеджера
        <Input
          onChange={(event) =>
            onManagerSearchChange(
              event.target.value,
            )
          }
          value={managerSearch}
        />
      </label>

      {managersLoading ? (
        <p role="status">
          Загружаем менеджеров…
        </p>
      ) : null}

      {managersError ? (
        <p role="alert">
          Не удалось загрузить
          менеджеров.{" "}
          <Button onClick={onRetry}>
            Повторить
          </Button>
        </p>
      ) : null}

      {!managersLoading
      && !managersError
      && managerOptions.length === 0 ? (
        <p>Менеджеры не найдены.</p>
      ) : null}

      <label>
        Новый менеджер
        <Select
          disabled={
            managersLoading
            || managersError
            || mutationPending
          }
          onChange={(event) =>
            onManagerChange(
              event.target.value,
            )
          }
          value={managerId}
        >
          <option value="">
            Выберите
          </option>

          {managerOptions
            .filter(
              (entry) =>
                entry.id
                !== current
                  .assigned_manager.id,
            )
            .map((entry) => (
              <option
                key={entry.id}
                value={entry.id}
              >
                {entry.display_name}
              </option>
            ))}
        </Select>
      </label>

      {managersHasNextPage ? (
        <Button
          className="button button--load-more"
          disabled={managersLoadingNext}
          onClick={onFetchMore}
        >
          {
            managersLoadingNext
              ? "Загружаем менеджеров…"
              : "Показать ещё менеджеров"
          }
        </Button>
      ) : null}

      <Button
        className="button button--dark"
        disabled={
          !managerId
          || managersError
          || mutationPending
        }
        onClick={() =>
          onAction(
            "transfer-manager",
            {
              expected_assigned_manager_user_id:
                current
                  .assigned_manager.id,
              manager_user_id:
                managerId,
            },
          )
        }
      >
        Передать
      </Button>
    </ProcurementDialog>
  );
}
