import {
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  useEffect,
  useState,
} from "react";
import {
  Link,
  useLocation,
  useParams,
} from "react-router-dom";

import {
  catalogQueryCacheKey,
  getCatalogCategory,
  getCatalogCategories,
  getCatalogFacetPage,
  getCatalogFacets,
} from "../../shared/api/catalog";
import {
  activeFilterCount,
  catalogFiltersFromViewState,
  defaultCatalogFilterState,
  toCatalogQuery,
} from "../../features/catalog/catalogQuery";
import {
  CatalogEmptyState,
  CatalogErrorState,
  CatalogListSkeleton,
} from "../../features/catalog/CatalogState";
import { EquipmentList } from "../../features/catalog/EquipmentList";
import { FilterSheet } from "../../features/catalog/FilterSheet";
import { DebouncedSearchField } from "../../features/catalog/DebouncedSearchField";
import {
  catalogDefaultSort,
  nextQuickSort,
  quickSortOptions,
  sortLabel,
} from "../../features/catalog/catalogSort";
import {
  SortSheet,
} from "../../features/catalog/SortSheet";
import { useCatalogItems } from "../../features/catalog/useCatalogItems";
import { useCatalogUrlState } from "../../features/catalog/useCatalogUrlState";
import { useInternalBackNavigation } from "../../features/navigation/useTelegramNavigation";
import { PageHeader } from "../../shared/ui";
import { useTelegramWebApp } from "../../shared/telegram/useTelegramWebApp";

export function CategoryPage() {
  const webApp = useTelegramWebApp();
  const queryClient = useQueryClient();
  const { categoryKey = "" } = useParams();
  const defaultSort =
    catalogDefaultSort(categoryKey);

  const {
    updateFilters,
    updateSearch,
    updateSort,
    viewState,
  } = useCatalogUrlState(defaultSort);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);
  const location = useLocation();
  const navigateBack = useInternalBackNavigation();
  const telegramOwnsBack = webApp?.BackButton !== undefined;
  const categoryQuery = useQuery({
    queryKey: ["catalog", "category", categoryKey],
    queryFn: ({ signal }) => getCatalogCategory(categoryKey, signal),
    enabled: categoryKey !== "",
    staleTime: 5 * 60_000,
  });
  const longRange = new URLSearchParams(location.search).get("long_range") === "true";
  const hierarchy = useQuery({
    queryKey: ["catalog", "categories"],
    queryFn: ({ signal }) => getCatalogCategories(signal),
    staleTime: 300_000,
  });
  const categorySummary = hierarchy.data?.find(
    (entry) => entry.key === categoryKey,
  );
  const categoryData = categoryQuery.data ?? categorySummary;
  const family = categoryData?.parent_id === null && !longRange;
  const categoryShapeKnown = longRange || categoryData !== undefined;
  const children = hierarchy.data?.filter(
    (child) => child.parent_id === categoryData?.id,
  ) ?? [];
  const familyId =
    family ? categoryData?.id : undefined;
  const catalogQuery = {
    ...toCatalogQuery(viewState, categoryKey),
    longRange,
  };
  const itemsQuery = useCatalogItems(
    catalogQuery,
    categoryKey !== ""
      && !categoryQuery.isError
      && categoryShapeKnown
      && !family,
  );
  const categoryContentPending =
    categoryQuery.isPending || itemsQuery.isPending;
  const facetsQuery = useQuery({
    queryKey: ["catalog", "facets", catalogQueryCacheKey(catalogQuery)],
    queryFn: ({ signal }) => getCatalogFacets(catalogQuery, signal),
    enabled: filtersOpen && categoryKey !== "",
  });
  const filtersCount = activeFilterCount(viewState);
  const quickSortHasSelection = quickSortOptions.some(
    (option) => option.sort === viewState.sort,
  );
  const returnTo = `${location.pathname}${location.search}`;

  useEffect(() => {
    window.scrollTo({
      top: 0,
      left: 0,
      behavior: "auto",
    });
  }, [categoryKey, longRange]);

  useEffect(() => {
    if (familyId === undefined) {
      return;
    }

    for (const child of hierarchy.data ?? []) {
      if (child.parent_id !== familyId) {
        continue;
      }

      void queryClient.prefetchQuery({
        queryKey: [
          "catalog",
          "category",
          child.key,
        ],
        queryFn: ({ signal }) =>
          getCatalogCategory(
            child.key,
            signal,
          ),
        staleTime: 5 * 60_000,
      });
    }
  }, [
    familyId,
    hierarchy.data,
    queryClient,
  ]);

  const clearAllFilters = () => {
    updateFilters(defaultCatalogFilterState);
  };

  return (
    <main className="catalog-page category-page">
      <PageHeader
        backLabel="Назад в каталог"
        description={categoryData?.description}
        kicker="Категория"
        onBack={
          !telegramOwnsBack
            ? navigateBack
            : undefined
        }
        title={
          longRange
            ? "Дальние трансиверы"
            : categoryData?.display_name
              ?? "Оборудование"
        }
      >
        {!family ? (
          <DebouncedSearchField
            busy={itemsQuery.isFetching}
            committedValue={viewState.q}
            label="Поиск внутри категории"
            onCommit={updateSearch}
            placeholder="Поиск внутри категории…"
          />
        ) : null}
      </PageHeader>

      <div className="catalog-page__body">
        {categoryQuery.isPending && categorySummary === undefined ? (
          <div className="category-title-skeleton" aria-label="Загрузка категории" />
        ) : null}
        {categoryQuery.isError ? (
          <CatalogErrorState
            title="Не удалось загрузить категорию"
            onRetry={() => void categoryQuery.refetch()}
          />
        ) : null}

        {categoryShapeKnown && family ? <div className="category-grid">
          {children.map(child => <Link key={child.id} className="category-tile" to={`/catalog/${child.key}`}><strong>{child.display_name}</strong>{child.description ? <p>{child.description}</p> : null}<i aria-hidden="true">↗</i></Link>)}
          {categoryKey === "transceivers" ? <Link className="category-tile" to="/catalog/transceivers?long_range=true"><strong>Дальние</strong><p>Дальность от 2 км.</p><i aria-hidden="true">↗</i></Link> : null}
        </div> : null}
        {categoryShapeKnown && !categoryQuery.isError && !family ? (
          <section aria-labelledby="category-items-title" className="catalog-section">
            <div className="result-toolbar">
              <div>
                <span className="section-kicker">Подходящие позиции</span>
                <h2 id="category-items-title">
                  {categoryContentPending ? "Загрузка" : `${itemsQuery.total} шт.`}
                </h2>
              </div>
              <div className="result-toolbar__actions">
                <button
                  className={
                    filtersCount > 0
                      ? "tool-button tool-button--active"
                      : "tool-button"
                  }
                  onClick={() => setFiltersOpen(true)}
                  type="button"
                >
                  Фильтры
                  {filtersCount > 0 ? (
                    <span>{filtersCount}</span>
                  ) : null}
                </button>

                <div
                  aria-label="Быстрая сортировка"
                  className="quick-sort"
                  role="group"
                >
                  {quickSortOptions.map((option) => {
                    const selected =
                      viewState.sort === option.sort;
                    const order = selected
                      ? viewState.order
                      : option.defaultOrder;

                    return (
                      <button
                        aria-pressed={selected}
                        className={
                          selected
                            ? "tool-button quick-sort__button quick-sort__button--active"
                            : "tool-button quick-sort__button"
                        }
                        key={option.sort}
                        onClick={() =>
                          updateSort(
                            nextQuickSort(
                              viewState,
                              option,
                            ),
                          )
                        }
                        type="button"
                      >
                        {option.label}
                        <span aria-hidden="true">
                          {order === "asc" ? "↑" : "↓"}
                        </span>
                      </button>
                    );
                  })}

                  <button
                    aria-label="Другие варианты сортировки"
                    aria-pressed={!quickSortHasSelection}
                    className={
                      !quickSortHasSelection
                        ? "tool-button quick-sort__more quick-sort__button--active"
                        : "tool-button quick-sort__more"
                    }
                    onClick={() => setSortOpen(true)}
                    type="button"
                  >
                    {quickSortHasSelection
                      ? "Ещё"
                      : sortLabel(viewState)}
                    <span aria-hidden="true">•••</span>
                  </button>
                </div>
              </div>
            </div>

            {categoryContentPending ? <CatalogListSkeleton /> : null}
            {itemsQuery.isError ? (
              <CatalogErrorState onRetry={() => void itemsQuery.refetch()} />
            ) : null}
            {!categoryContentPending && !itemsQuery.isError && itemsQuery.items.length === 0 ? (
              <CatalogEmptyState
                action={filtersCount > 0 ? (
                  <button className="button button--ghost" onClick={clearAllFilters} type="button">
                    Сбросить фильтры
                  </button>
                ) : undefined}
                title={filtersCount > 0 ? "По фильтрам ничего нет" : viewState.q ? "Ничего не найдено" : "В категории пока пусто"}
              >
                {filtersCount > 0
                  ? "Измените параметры или очистите фильтры."
                  : viewState.q
                    ? "Попробуйте изменить поисковый запрос."
                    : "Позиции появятся после наполнения каталога."}
              </CatalogEmptyState>
            ) : null}
            {!categoryContentPending && itemsQuery.items.length > 0 ? (
              <>
                {itemsQuery.isFetching && !itemsQuery.isFetchingNextPage ? (
                  <p className="background-status" role="status">Обновляем список…</p>
                ) : null}
                <EquipmentList
                  attributes={categoryQuery.data?.attributes}
                  items={itemsQuery.items}
                  returnTo={returnTo}
                />
                {itemsQuery.hasNextPage ? (
                  <button
                    className="button button--load-more"
                    disabled={itemsQuery.isFetchingNextPage}
                    onClick={() => void itemsQuery.fetchNextPage()}
                    type="button"
                  >
                    {itemsQuery.isFetchingNextPage ? "Загружаем…" : "Показать ещё"}
                  </button>
                ) : null}
              </>
            ) : null}
          </section>
        ) : null}
      </div>

      {filtersOpen ? (
        <FilterSheet
          active={catalogFiltersFromViewState(viewState)}
          attributes={categoryQuery.data?.attributes ?? []}
          error={facetsQuery.isError}
          facets={facetsQuery.data?.facets ?? []}
          loading={facetsQuery.isPending}
          onApply={(next) => {
            updateFilters(next);
            setFiltersOpen(false);
          }}
          onCancel={() => setFiltersOpen(false)}
          onLoadMore={async (facetKey, offset) => {
            const page = await getCatalogFacetPage(
              catalogQuery,
              {
                facet: facetKey,
                offset,
              },
            );
            const nextFacet = page.facets[0];
            if (nextFacet === undefined || nextFacet.key !== facetKey) {
              throw new Error(
                `Facet page mismatch for ${facetKey}`,
              );
            }
            return nextFacet;
          }}
          onRetry={() => void facetsQuery.refetch()}
        />
      ) : null}
      {sortOpen ? (
        <SortSheet
          active={viewState}
          onCancel={() => setSortOpen(false)}
          onSelect={(selection) => {
            updateSort(selection);
            setSortOpen(false);
          }}
        />
      ) : null}
    </main>
  );
}
