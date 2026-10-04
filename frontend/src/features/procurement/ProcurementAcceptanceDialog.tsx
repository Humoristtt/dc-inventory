import {
  Button,
  Select,
} from "../../shared/ui";
import type {
  StorageLocation,
} from "../../shared/api/inventory";
import type {
  ProcurementRequest,
} from "../../shared/api/procurement";
import {
  ProcurementDialog,
} from "./ProcurementDialog";
import {
  procurementLineTitle,
} from "./procurementDetailModel";
import type {
  ProcurementAction,
} from "./procurementDetailDialogTypes";

export function ProcurementAcceptanceDialog({
  activeLocations,
  current,
  locationId,
  locationsError,
  locationsLoading,
  mutationPending,
  open,
  onAction,
  onClose,
  onLocationChange,
  onRetryLocations,
}: {
  activeLocations:
    readonly StorageLocation[];
  current: ProcurementRequest;
  locationId: string;
  locationsError: boolean;
  locationsLoading: boolean;
  mutationPending: boolean;
  open: boolean;
  onAction: ProcurementAction;
  onClose: () => void;
  onLocationChange:
    (value: string) => void;
  onRetryLocations:
    () => void;
}) {
  return (
    <ProcurementDialog
      onClose={onClose}
      open={open}
      title="Подтвердить приёмку"
    >
      <p>
        После подтверждения на склад
        будет добавлено:
      </p>

      <ul>
        {current
          .current_revision
          .lines
          .map((line) => (
            <li key={line.id}>
              {
                procurementLineTitle(
                  line,
                )
              }
              {" — "}
              {line.quantity} шт.
            </li>
          ))}
      </ul>

      {locationsLoading ? (
        <p role="status">
          Загружаем места приёмки…
        </p>
      ) : null}

      {locationsError ? (
        <p role="alert">
          Не удалось загрузить
          места приёмки.{" "}
          <Button
            onClick={onRetryLocations}
          >
            Повторить
          </Button>
        </p>
      ) : null}

      {!locationsLoading
      && !locationsError
      && activeLocations.length === 0 ? (
        <p>
          Нет доступных мест приёмки.
        </p>
      ) : null}

      <label>
        Место приёмки
        <Select
          disabled={
            locationsLoading
            || locationsError
            || mutationPending
          }
          onChange={(event) =>
            onLocationChange(
              event.target.value,
            )
          }
          value={locationId}
        >
          <option value="">
            Выберите
          </option>

          {activeLocations.map(
            (entry) => (
              <option
                key={entry.id}
                value={entry.id}
              >
                {entry.name}
                {" · "}
                {entry.code}
              </option>
            ),
          )}
        </Select>
      </label>

      <Button
        className="button button--accent"
        disabled={
          !locationId
          || locationsError
          || mutationPending
          || current
            .current_revision
            .lines.some(
              (line) =>
                !line.bound_item_id,
            )
        }
        onClick={() =>
          onAction(
            "acceptance",
            {
              receiving_location_id:
                locationId,
            },
          )
        }
      >
        Подтвердить и оприходовать
      </Button>
    </ProcurementDialog>
  );
}
