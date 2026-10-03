import {
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  useEffect,
  useState,
} from "react";
import {
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
import { FilterSheet } from "../../features/catalog/FilterSheet";
import { DebouncedSearchField } from "../../features/catalog/DebouncedSearchField";
import { CatalogErrorState } from "../../features/catalog/CatalogState";
import {
  catalogDefaultSort,
  quickSortOptions,
  sortOptionsForContext,
} from "../../features/catalog/catalogSort";
import {
  SortSheet,
} from "../../features/catalog/SortSheet";
import { useCatalogItems } from "../../features/catalog/useCatalogItems";
import {

} from "../../features/catalog/transceiverFilters";
import { useCatalogUrlState } from "../../features/catalog/useCatalogUrlState";
import { CategoryFamilyGrid } from "../../features/catalog/CategoryFamilyGrid";
import { CategoryResults } from "../../features/catalog/CategoryResults";
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
  const viewParams = new URLSearchParams(
    location.search,
  );
  const longRange =
    viewParams.get("long_range") === "true";
  const rj45 =
    viewParams.get("rj45") === "true";
  const navigateBack = useInternalBackNavigation();
  const telegramOwnsBack = webApp?.BackButton !== undefined;
  const categoryQuery = useQuery({
    queryKey: ["catalog", "category", categoryKey],
    queryFn: ({ signal }) => getCatalogCategory(categoryKey, signal),
    enabled: categoryKey !== "",
    staleTime: 5 * 60_000,
  });
  const hierarchy = useQuery({
    queryKey: ["catalog", "categories"],
    queryFn: ({ signal }) => getCatalogCategories(signal),
    staleTime: 300_000,
  });
  const categorySummary = hierarchy.data?.find(
    (entry) => entry.key === categoryKey,
  );
  const categoryData = categoryQuery.data ?? categorySummary;
  const family =
    categoryData?.parent_id === null
    && !longRange
    && !rj45;
  const categoryShapeKnown =
    longRange
    || rj45
    || categoryData !== undefined;
  const children = hierarchy.data?.filter(
    (child) => child.parent_id === categoryData?.id,
  ) ?? [];
  const familyId =
    family ? categoryData?.id : undefined;
  const catalogQuery = {
    ...toCatalogQuery(viewState, categoryKey),
    longRange,
    rj45,
  };
  const ethernetSpeedView =
    categoryKey === "transceiver_ethernet"
    && !longRange
    && !rj45;
  const speedFacetQueryBase = {
    ...catalogQuery,
    filters: catalogQuery.filters?.filter(
      (filter) => filter.key !== "speed",
    ),
  };
  const speedFacetQuery = useQuery({
    queryKey: [
      "catalog",
      "ethernet-speed-buckets",
      catalogQueryCacheKey(speedFacetQueryBase),
    ],
    queryFn: async ({ signal }) => {
      const page = await getCatalogFacetPage(
        speedFacetQueryBase,
        {
          facet: "speed",
          limit: 100,
        },
        signal,
      );
      return page.facets.find(
        (facet) => facet.key === "speed",
      );
    },
    enabled:
      ethernetSpeedView
      && !categoryQuery.isError,
    staleTime: 60_000,
  });
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
  const speedFilterCount = viewState.filters.filter(
    (filter) =>
      filter.key === "speed"
      && filter.operator === "eq",
  ).length;
  const filtersCount =
    activeFilterCount(viewState)
    - Math.max(0, speedFilterCount - 1);
  const quickSortChoices = quickSortOptions(
    categoryKey,
    longRange,
  );
  const sortSheetOptions =
    sortOptionsForContext(
      categoryKey,
      longRange,
      viewState.q.trim() !== "",
    );
  const quickSortHasSelection = quickSortChoices.some(
    (option) => option.sort === viewState.sort,
  );
  const returnTo = `${location.pathname}${location.search}`;

  useEffect(() => {
    window.scrollTo({
      top: 0,
      left: 0,
      behavior: "auto",
    });
  }, [categoryKey, longRange, rj45]);

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
        description={
          rj45
            ? "Медные SFP/SFP+ трансиверы с разъёмом RJ-45."
            : categoryData?.description
        }
        kicker="Категория"
        onBack={
          !telegramOwnsBack
            ? navigateBack
            : undefined
        }
        title={
          rj45
            ? "RJ-45 SFP"
            : longRange
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

        {categoryShapeKnown && family ? (
          <CategoryFamilyGrid
            categories={children}
            categoryKey={categoryKey}
          />
        ) : null}

        {
          categoryShapeKnown
          && !categoryQuery.isError
          && !family
            ? (
                <CategoryResults
                  attributes={
                    categoryQuery.data
                      ?.attributes
                  }
                  error={
                    itemsQuery.isError
                  }
                  ethernetSpeedView={
                    ethernetSpeedView
                  }
                  fetching={
                    itemsQuery.isFetching
                  }
                  fetchingNext={
                    itemsQuery
                      .isFetchingNextPage
                  }
                  filtersCount={
                    filtersCount
                  }
                  hasNextPage={
                    itemsQuery.hasNextPage
                    ?? false
                  }
                  items={
                    itemsQuery.items
                  }
                  loading={
                    categoryContentPending
                  }
                  onClearFilters={
                    clearAllFilters
                  }
                  onFetchNext={() =>
                    void itemsQuery
                      .fetchNextPage()
                  }
                  onOpenFilters={() =>
                    setFiltersOpen(true)
                  }
                  onOpenSort={() =>
                    setSortOpen(true)
                  }
                  onRetry={() =>
                    void itemsQuery.refetch()
                  }
                  onUpdateFilters={
                    updateFilters
                  }
                  onUpdateSort={
                    updateSort
                  }
                  quickSortChoices={
                    quickSortChoices
                  }
                  quickSortHasSelection={
                    quickSortHasSelection
                  }
                  returnTo={returnTo}
                  speedFacet={
                    speedFacetQuery.data
                  }
                  speedFacetPending={
                    speedFacetQuery
                      .isPending
                  }
                  total={
                    itemsQuery.total
                  }
                  viewState={
                    viewState
                  }
                />
              )
            : null
        }
      </div>

      {filtersOpen ? (
        <FilterSheet
          active={catalogFiltersFromViewState(viewState)}
          attributes={categoryQuery.data?.attributes ?? []}
          error={facetsQuery.isError}
          facets={
            (facetsQuery.data?.facets ?? []).filter(
              (facet) =>
                !ethernetSpeedView
                || facet.key !== "speed",
            )
          }
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
          options={sortSheetOptions}
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
