import {
  Button,
  Input,
} from "../../shared/ui";
import type {
  CatalogItemListEntry,
} from "../../shared/api/catalog";
import {
  ProcurementDialog,
} from "./ProcurementDialog";
import type {
  ProcurementAction,
} from "./procurementDetailDialogTypes";

export function ProcurementBindingDialog({
  bindingItemsError,
  bindingItemsHasNextPage,
  bindingItemsLoading,
  bindingItemsLoadingNext,
  bindingItemOptions,
  bindingLine,
  bindingSearch,
  mutationPending,
  onAction,
  onBindingSearchChange,
  onClose,
  onFetchMore,
  onRetry,
}: {
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
  mutationPending: boolean;
  onAction: ProcurementAction;
  onBindingSearchChange:
    (value: string) => void;
  onClose: () => void;
  onFetchMore: () => void;
  onRetry: () => void;
}) {
  return (
    <ProcurementDialog
      onClose={onClose}
      open={bindingLine !== null}
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

      {bindingSearch.trim().length < 2 ? (
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
          <Button onClick={onRetry}>
            Повторить
          </Button>
        </p>
      ) : null}

      {bindingSearch.trim().length >= 2
      && !bindingItemsLoading
      && !bindingItemsError
      && bindingItemOptions.length === 0 ? (
        <p>
          Оборудование не найдено.
        </p>
      ) : null}

      <div className="procurement-binding-results">
        {bindingItemOptions.map(
          (item) => (
            <Button
              className="button"
              disabled={mutationPending}
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
          onClick={onFetchMore}
        >
          {
            bindingItemsLoadingNext
              ? "Загружаем…"
              : "Показать ещё"
          }
        </Button>
      ) : null}
    </ProcurementDialog>
  );
}
