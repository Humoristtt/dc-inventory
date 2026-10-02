import {
  Button,
} from "../../shared/ui";
import type {
  CatalogFacet,
  CatalogItemListEntry,
  CategoryAttribute,
} from "../../shared/api/catalog";
import {
  CatalogEmptyState,
  CatalogErrorState,
  CatalogListSkeleton,
} from "./CatalogState";
import {
  EquipmentList,
} from "./EquipmentList";
import {
  catalogFiltersFromViewState,
  type CatalogFilterState,
  type CatalogSortState,
  type CatalogViewState,
} from "./catalogQuery";
import {
  nextQuickSort,
  sortLabel,
  type QuickSortOption,
} from "./catalogSort";
import {
  ETHERNET_SPEED_BUCKETS,
  isSpeedBucketSelected,
  speedFacetValuesForBucket,
  toggleSpeedBucket,
} from "./transceiverFilters";

export function CategoryResults({
  attributes,
  ethernetSpeedView,
  error,
  fetching,
  fetchingNext,
  filtersCount,
  hasNextPage,
  items,
  loading,
  quickSortChoices,
  quickSortHasSelection,
  returnTo,
  speedFacet,
  speedFacetPending,
  total,
  viewState,
  onClearFilters,
  onFetchNext,
  onOpenFilters,
  onOpenSort,
  onRetry,
  onUpdateFilters,
  onUpdateSort,
}: {
  attributes:
    readonly CategoryAttribute[]
    | undefined;
  ethernetSpeedView: boolean;
  error: boolean;
  fetching: boolean;
  fetchingNext: boolean;
  filtersCount: number;
  hasNextPage: boolean;
  items:
    readonly CatalogItemListEntry[];
  loading: boolean;
  quickSortChoices:
    readonly QuickSortOption[];
  quickSortHasSelection: boolean;
  returnTo: string;
  speedFacet:
    CatalogFacet
    | undefined;
  speedFacetPending: boolean;
  total: number;
  viewState: CatalogViewState;
  onClearFilters: () => void;
  onFetchNext: () => void;
  onOpenFilters: () => void;
  onOpenSort: () => void;
  onRetry: () => void;
  onUpdateFilters: (
    next: CatalogFilterState,
  ) => void;
  onUpdateSort: (
    next: CatalogSortState,
  ) => void;
}) {
  return (
    <section
      aria-labelledby="category-items-title"
      className="catalog-section"
    >
      <div className="result-toolbar">
        <div>
          <span className="section-kicker">
            Подходящие позиции
          </span>
          <h2 id="category-items-title">
            {
              loading
                ? "Загрузка"
                : `${total} шт.`
            }
          </h2>
        </div>

        <div className="result-toolbar__actions">
          {ethernetSpeedView ? (
            <div
              aria-label="Скорость Ethernet-трансивера"
              className="transceiver-speed-filter"
              role="group"
            >
              {ETHERNET_SPEED_BUCKETS.map(
                (bucket) => {
                  const values =
                    speedFacetValuesForBucket(
                      speedFacet,
                      bucket,
                    );
                  const selected =
                    isSpeedBucketSelected(
                      viewState.filters,
                      values,
                    );

                  return (
                    <Button
                      aria-pressed={
                        selected
                      }
                      className={
                        selected
                          ? "tool-button transceiver-speed-filter__button quick-sort__button--active"
                          : "tool-button transceiver-speed-filter__button"
                      }
                      disabled={
                        speedFacetPending
                        || values.length
                          === 0
                      }
                      key={bucket}
                      onClick={() => {
                        const current =
                          catalogFiltersFromViewState(
                            viewState,
                          );

                        onUpdateFilters({
                          ...current,
                          filters:
                            toggleSpeedBucket(
                              current.filters,
                              speedFacet,
                              bucket,
                            ),
                        });
                      }}
                    >
                      {bucket}
                    </Button>
                  );
                },
              )}
            </div>
          ) : null}

          {ethernetSpeedView ? (
            <Button
              className="tool-button"
              disabled={
                filtersCount === 0
              }
              onClick={onClearFilters}
            >
              Сбросить фильтры
            </Button>
          ) : (
            <Button
              className={
                filtersCount > 0
                  ? "tool-button tool-button--active"
                  : "tool-button"
              }
              onClick={onOpenFilters}
            >
              Фильтры
              {filtersCount > 0 ? (
                <span>
                  {filtersCount}
                </span>
              ) : null}
            </Button>
          )}

          <div
            aria-label="Быстрая сортировка"
            className="quick-sort"
            role="group"
          >
            {quickSortChoices.map(
              (option) => {
                const selected =
                  viewState.sort
                  === option.sort;
                const order = selected
                  ? viewState.order
                  : option.defaultOrder;

                return (
                  <Button
                    aria-pressed={
                      selected
                    }
                    className={
                      selected
                        ? "tool-button quick-sort__button quick-sort__button--active"
                        : "tool-button quick-sort__button"
                    }
                    key={option.sort}
                    onClick={() =>
                      onUpdateSort(
                        nextQuickSort(
                          viewState,
                          option,
                        ),
                      )
                    }
                  >
                    {option.label}
                    <span
                      aria-hidden="true"
                    >
                      {
                        order === "asc"
                          ? "↑"
                          : "↓"
                      }
                    </span>
                  </Button>
                );
              },
            )}

            {!ethernetSpeedView ? (
              <Button
                aria-label="Другие варианты сортировки"
                aria-pressed={
                  !quickSortHasSelection
                }
                className={
                  !quickSortHasSelection
                    ? "tool-button quick-sort__more quick-sort__button--active"
                    : "tool-button quick-sort__more"
                }
                onClick={onOpenSort}
              >
                {
                  quickSortHasSelection
                    ? "Ещё"
                    : sortLabel(
                        viewState,
                      )
                }
                <span aria-hidden="true">
                  •••
                </span>
              </Button>
            ) : null}
          </div>
        </div>
      </div>

      {loading ? (
        <CatalogListSkeleton />
      ) : null}

      {error ? (
        <CatalogErrorState
          onRetry={onRetry}
        />
      ) : null}

      {!loading
      && !error
      && items.length === 0 ? (
        <CatalogEmptyState
          action={
            filtersCount > 0
              ? (
                  <Button
                    className="button button--ghost"
                    onClick={
                      onClearFilters
                    }
                  >
                    Сбросить фильтры
                  </Button>
                )
              : undefined
          }
          title={
            filtersCount > 0
              ? "По фильтрам ничего нет"
              : viewState.q
                ? "Ничего не найдено"
                : "В категории пока пусто"
          }
        >
          {
            filtersCount > 0
              ? "Измените параметры или очистите фильтры."
              : viewState.q
                ? "Попробуйте изменить поисковый запрос."
                : "Позиции появятся после наполнения каталога."
          }
        </CatalogEmptyState>
      ) : null}

      {!loading
      && items.length > 0 ? (
        <>
          {
            fetching
            && !fetchingNext
              ? (
                  <p
                    className="background-status"
                    role="status"
                  >
                    Обновляем список…
                  </p>
                )
              : null
          }

          <EquipmentList
            attributes={
              attributes
                ? [...attributes]
                : undefined
            }
            items={[...items]}
            returnTo={returnTo}
          />

          {hasNextPage ? (
            <Button
              className="button button--load-more"
              disabled={fetchingNext}
              onClick={onFetchNext}
            >
              {
                fetchingNext
                  ? "Загружаем…"
                  : "Показать ещё"
              }
            </Button>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
