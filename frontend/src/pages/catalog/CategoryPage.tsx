import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
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
import { sortLabel } from "../../features/catalog/catalogSort";
import {
  SortSheet,
} from "../../features/catalog/SortSheet";
import { useCatalogItems } from "../../features/catalog/useCatalogItems";
import { useCatalogUrlState } from "../../features/catalog/useCatalogUrlState";
import { useInternalBackNavigation } from "../../features/navigation/useTelegramNavigation";
import { SpikatelBrand } from "../../shared/brand/SpikatelBrand";
import { TelegramFullscreenButton } from "../../shared/telegram/TelegramFullscreenButton";
import { getTelegramWebApp } from "../../shared/telegram/webApp";

export function CategoryPage() {
  const { categoryKey = "" } = useParams();
  const {
    updateFilters,
    updateSearch,
    updateSort,
    viewState,
  } = useCatalogUrlState();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);
  const location = useLocation();
  const navigateBack = useInternalBackNavigation();
  const telegramOwnsBack = getTelegramWebApp()?.BackButton !== undefined;
  const categoryQuery = useQuery({
    queryKey: ["catalog", "category", categoryKey],
    queryFn: ({ signal }) => getCatalogCategory(categoryKey, signal),
    enabled: categoryKey !== "",
    staleTime: 5 * 60_000,
  });
  const longRange = new URLSearchParams(location.search).get("long_range") === "true";
  const hierarchy = useQuery({queryKey: ["catalog", "categories"], queryFn: ({signal}) => getCatalogCategories(signal), staleTime: 300_000});
  const family = categoryQuery.data?.parent_id === null && !longRange;
  const children = hierarchy.data?.filter(child => child.parent_id === categoryQuery.data?.id) ?? [];
  const catalogQuery = {...toCatalogQuery(viewState, categoryKey), longRange};
  const itemsQuery = useCatalogItems(catalogQuery, categoryKey !== "" && categoryQuery.isSuccess && !family);
  const facetsQuery = useQuery({
    queryKey: ["catalog", "facets", catalogQueryCacheKey(catalogQuery)],
    queryFn: ({ signal }) => getCatalogFacets(catalogQuery, signal),
    enabled: filtersOpen && categoryKey !== "",
  });
  const filtersCount = activeFilterCount(viewState);
  const returnTo = `${location.pathname}${location.search}`;

  const clearAllFilters = () => {
    updateFilters(defaultCatalogFilterState);
  };

  return (
    <main className="catalog-page category-page">
      <header className="category-header">
        <div className="page-toolbar">
          {!telegramOwnsBack ? (
            <button
              aria-label="Назад в каталог"
              className="icon-button icon-button--light"
              onClick={navigateBack}
              type="button"
            >
              ←
            </button>
          ) : null}
          <SpikatelBrand inverse title="Инвентаризация ЦОД" />
          <TelegramFullscreenButton />
        </div>
        <div className="category-header__title">
          <span className="section-kicker">Категория</span>
          <h1>{longRange ? "Дальние трансиверы" : categoryQuery.data?.display_name ?? "Оборудование"}</h1>
          {categoryQuery.data?.description ? <p>{categoryQuery.data.description}</p> : null}
        </div>
        {!family ? <DebouncedSearchField
          busy={itemsQuery.isFetching}
          committedValue={viewState.q}
          label="Поиск внутри категории"
          onCommit={updateSearch}
          placeholder="Поиск внутри категории…"
        /> : null}
      </header>

      <div className="catalog-page__body">
        {categoryQuery.isPending ? (
          <div className="category-title-skeleton" aria-label="Загрузка категории" />
        ) : null}
        {categoryQuery.isError ? (
          <CatalogErrorState
            title="Не удалось загрузить категорию"
            onRetry={() => void categoryQuery.refetch()}
          />
        ) : null}

        {family ? <div className="category-grid">
          {children.map(child => <Link key={child.id} className="category-tile" to={`/catalog/${child.key}`}><strong>{child.display_name}</strong><i aria-hidden="true">↗</i></Link>)}
          {categoryKey === "transceivers" ? <Link className="category-tile" to="/catalog/transceivers?long_range=true"><strong>Дальние</strong><p>Дальность от 2 км.</p><i aria-hidden="true">↗</i></Link> : null}
        </div> : null}
        {!categoryQuery.isError && !family ? (
          <section aria-labelledby="category-items-title" className="catalog-section">
            <div className="result-toolbar">
              <div>
                <span className="section-kicker">Подходящие позиции</span>
                <h2 id="category-items-title">
                  {itemsQuery.isPending ? "Загрузка" : `${itemsQuery.total} шт.`}
                </h2>
              </div>
              <div className="result-toolbar__actions">
                <button
                  className={filtersCount > 0 ? "tool-button tool-button--active" : "tool-button"}
                  onClick={() => setFiltersOpen(true)}
                  type="button"
                >
                  Фильтры
                  {filtersCount > 0 ? <span>{filtersCount}</span> : null}
                </button>
                <button className="tool-button" onClick={() => setSortOpen(true)} type="button">
                  {sortLabel(viewState)}
                  <span aria-hidden="true">↕</span>
                </button>
              </div>
            </div>

            {itemsQuery.isPending ? <CatalogListSkeleton /> : null}
            {itemsQuery.isError ? (
              <CatalogErrorState onRetry={() => void itemsQuery.refetch()} />
            ) : null}
            {!itemsQuery.isPending && !itemsQuery.isError && itemsQuery.items.length === 0 ? (
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
            {itemsQuery.items.length > 0 ? (
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
