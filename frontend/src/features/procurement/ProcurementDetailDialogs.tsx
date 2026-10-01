import {
  Button,
  Input,
  Select,
  Textarea,
} from "../../shared/ui";
import {
  LineComposer,
} from "./LineComposer";
import {
  ProcurementDialog,
} from "./ProcurementDialog";
import type {
  CatalogItemListEntry,
} from "../../shared/api/catalog";
import type {
  StorageLocation,
} from "../../shared/api/inventory";
import type {
  ProcurementLineInput,
  ProcurementRequest,
  UserSummary,
} from "../../shared/api/procurement";
import type {
  ProcurementDialogKind,
} from "./ProcurementActionBar";
import {
  procurementLineTitle,
} from "./procurementDetailModel";

export type ProcurementAction =
  (
    action: string,
    extra?:
      Record<string, unknown>,
  ) => void;

export function ProcurementDetailDialogs({
  activeLocations,
  bindingItemsError,
  bindingItemsHasNextPage,
  bindingItemsLoading,
  bindingItemsLoadingNext,
  bindingItemOptions,
  bindingLine,
  bindingSearch,
  comment,
  current,
  dialog,
  locationId,
  locationsError,
  locationsLoading,
  managerId,
  managerOptions,
  managerSearch,
  managersError,
  managersHasNextPage,
  managersLoading,
  managersLoadingNext,
  mutationPending,
  proposal,
  revisionLines,
  onAction,
  onBindingSearchChange,
  onCloseDialog,
  onCommentChange,
  onFetchMoreBindingItems,
  onFetchMoreManagers,
  onLocationChange,
  onManagerChange,
  onManagerSearchChange,
  onProposalChange,
  onRetryBindingItems,
  onRetryLocations,
  onRetryManagers,
  onRevisionLinesChange,
  onSetBindingLine,
}: {
  activeLocations:
    readonly StorageLocation[];
  bindingItemsError: boolean;
  bindingItemsHasNextPage: boolean;
  bindingItemsLoading: boolean;
  bindingItemsLoadingNext: boolean;
  bindingItemOptions:
    readonly CatalogItemListEntry[];
  bindingLine:
    | string
    | null;
  bindingSearch: string;
  comment: string;
  current: ProcurementRequest;
  dialog:
    | ProcurementDialogKind
    | null;
  locationId: string;
  locationsError: boolean;
  locationsLoading: boolean;
  managerId: string;
  managerOptions:
    readonly UserSummary[];
  managerSearch: string;
  managersError: boolean;
  managersHasNextPage: boolean;
  managersLoading: boolean;
  managersLoadingNext: boolean;
  mutationPending: boolean;
  proposal:
    ProcurementLineInput[];
  revisionLines:
    ProcurementLineInput[];
  onAction: ProcurementAction;
  onBindingSearchChange:
    (value: string) => void;
  onCloseDialog: () => void;
  onCommentChange:
    (value: string) => void;
  onFetchMoreBindingItems:
    () => void;
  onFetchMoreManagers:
    () => void;
  onLocationChange:
    (value: string) => void;
  onManagerChange:
    (value: string) => void;
  onManagerSearchChange:
    (value: string) => void;
  onProposalChange:
    (lines:
      ProcurementLineInput[],
    ) => void;
  onRetryBindingItems:
    () => void;
  onRetryLocations:
    () => void;
  onRetryManagers:
    () => void;
  onRevisionLinesChange:
    (lines:
      ProcurementLineInput[],
    ) => void;
  onSetBindingLine:
    (
      lineId:
        | string
        | null,
    ) => void;
}) {
  return (
    <>
      <ProcurementDialog
        onClose={onCloseDialog}
        open={
          dialog === "transfer"
        }
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
            <Button
              onClick={
                onRetryManagers
              }
            >
              Повторить
            </Button>
          </p>
        ) : null}

        {!managersLoading
        && !managersError
        && managerOptions.length
          === 0 ? (
            <p>
              Менеджеры не найдены.
            </p>
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
                    .assigned_manager
                    .id,
              )
              .map((entry) => (
                <option
                  key={entry.id}
                  value={entry.id}
                >
                  {
                    entry.display_name
                  }
                </option>
              ))}
          </Select>
        </label>

        {managersHasNextPage ? (
          <Button
            className="button button--load-more"
            disabled={
              managersLoadingNext
            }
            onClick={
              onFetchMoreManagers
            }
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
                    .assigned_manager
                    .id,
                manager_user_id:
                  managerId,
              },
            )
          }
        >
          Передать
        </Button>
      </ProcurementDialog>

      <ProcurementDialog
        onClose={onCloseDialog}
        open={
          dialog === "correction"
        }
        title="Вернуть на корректировку"
      >
        <label>
          Комментарий
          <Textarea
            maxLength={4000}
            onChange={(event) =>
              onCommentChange(
                event.target.value,
              )
            }
            value={comment}
          />
        </label>

        <details>
          <summary>
            Добавить альтернативный
            состав
          </summary>
          <LineComposer
            lines={proposal}
            onChange={
              onProposalChange
            }
          />
        </details>

        <Button
          className="button button--danger"
          disabled={
            !comment.trim()
            || mutationPending
          }
          onClick={() =>
            onAction(
              "return-for-correction",
              {
                comment,
                alternative_proposal:
                  proposal.length
                    ? proposal
                    : null,
              },
            )
          }
        >
          Вернуть
        </Button>
      </ProcurementDialog>

      <ProcurementDialog
        onClose={onCloseDialog}
        open={
          dialog === "revision"
        }
        title="Новая редакция"
      >
        <LineComposer
          lines={revisionLines}
          onChange={
            onRevisionLinesChange
          }
        />

        <label>
          Комментарий
          <Textarea
            maxLength={4000}
            onChange={(event) =>
              onCommentChange(
                event.target.value,
              )
            }
            value={comment}
          />
        </label>

        <Button
          className="button button--accent"
          disabled={
            !revisionLines.length
            || mutationPending
          }
          onClick={() =>
            onAction(
              "revisions",
              {
                lines:
                  revisionLines,
                general_comment:
                  comment.trim()
                  || null,
              },
            )
          }
        >
          Отправить редакцию
        </Button>
      </ProcurementDialog>

      <ProcurementDialog
        onClose={onCloseDialog}
        open={
          dialog
          === "discrepancy"
        }
        title="Есть расхождения"
      >
        <label>
          Что отличается
          <Textarea
            maxLength={4000}
            onChange={(event) =>
              onCommentChange(
                event.target.value,
              )
            }
            value={comment}
          />
        </label>

        <Button
          className="button button--danger"
          disabled={
            !comment.trim()
            || mutationPending
          }
          onClick={() =>
            onAction(
              "discrepancies",
              { comment },
            )
          }
        >
          Зафиксировать
        </Button>
      </ProcurementDialog>

      <ProcurementDialog
        onClose={onCloseDialog}
        open={
          dialog === "accept"
        }
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
              onClick={
                onRetryLocations
              }
            >
              Повторить
            </Button>
          </p>
        ) : null}

        {!locationsLoading
        && !locationsError
        && activeLocations.length
          === 0 ? (
            <p>
              Нет доступных мест
              приёмки.
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

      <ProcurementDialog
        onClose={() =>
          onSetBindingLine(null)
        }
        open={
          bindingLine !== null
        }
        title="Связать с каталогом"
      >
        <label>
          Поиск
          <Input
            onChange={(event) =>
              onBindingSearchChange(
                event.target.value,
              )
            }
            value={bindingSearch}
          />
        </label>

        {bindingSearch.trim().length
        < 2 ? (
          <p>
            Введите минимум 2 символа
            для поиска.
          </p>
        ) : null}

        {bindingItemsLoading ? (
          <p role="status">
            Ищем оборудование…
          </p>
        ) : null}

        {bindingItemsError ? (
          <p role="alert">
            Не удалось загрузить
            оборудование.{" "}
            <Button
              onClick={
                onRetryBindingItems
              }
            >
              Повторить
            </Button>
          </p>
        ) : null}

        {bindingSearch.trim().length
          >= 2
        && !bindingItemsLoading
        && !bindingItemsError
        && bindingItemOptions.length
          === 0 ? (
            <p>
              Оборудование
              не найдено.
            </p>
          ) : null}

        <div className="procurement-binding-results">
          {bindingItemOptions.map(
            (item) => (
              <Button
                className="button"
                disabled={
                  mutationPending
                }
                key={item.id}
                onClick={() =>
                  onAction(
                    "bind-line",
                    {
                      line_id:
                        bindingLine,
                      item_id:
                        item.id,
                    },
                  )
                }
              >
                {[
                  item.manufacturer
                    ?.name,
                  item.name,
                  item.model,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </Button>
            ),
          )}
        </div>

        {bindingItemsHasNextPage ? (
          <Button
            className="button button--load-more"
            disabled={
              bindingItemsLoadingNext
            }
            onClick={
              onFetchMoreBindingItems
            }
          >
            {
              bindingItemsLoadingNext
                ? "Загружаем…"
                : "Показать ещё"
            }
          </Button>
        ) : null}
      </ProcurementDialog>
    </>
  );
}
