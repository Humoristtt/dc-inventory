import { useQuery } from "@tanstack/react-query";
import {
  Link,
  useLocation,
} from "react-router-dom";

import { useAuthState } from "../../features/auth/useAuthState";
import {
  getCatalogCategories,
} from "../../shared/api/catalog";
import {
  toCatalogQuery,
} from "../../features/catalog/catalogQuery";
import {
  CatalogEmptyState,
  CatalogErrorState,
  CatalogListSkeleton,
} from "../../features/catalog/CatalogState";
import { EquipmentList } from "../../features/catalog/EquipmentList";
import { DebouncedSearchField } from "../../features/catalog/DebouncedSearchField";
import { useCatalogUrlState } from "../../features/catalog/useCatalogUrlState";
import { useCatalogItems } from "../../features/catalog/useCatalogItems";
import { SpikatelBrand } from "../../shared/brand/SpikatelBrand";
import "../../features/catalog/catalog.css";

export function CatalogLandingPage() {
  const { updateSearch, viewState } = useCatalogUrlState();
  const location = useLocation();
  const authQuery = useAuthState();

  const categoriesQuery = useQuery({
    queryKey: ["catalog", "categories"],
    queryFn: ({ signal }) => getCatalogCategories(signal),
    staleTime: 5 * 60_000,
  });
  const searchActive = viewState.q !== "";
  const itemsQuery = useCatalogItems(toCatalogQuery(viewState), searchActive);
  const returnTo = `${location.pathname}${location.search}`;

  return (
    <main className="catalog-page catalog-page--landing">
      <header className="catalog-landing-header">
        <SpikatelBrand inverse subtitle="Оборудование ЦОД" />
        <div className="catalog-landing-header__copy">
          <span className="section-kicker">Рабочий каталог</span>
          <h1>Найти оборудование</h1>
        </div>
        <DebouncedSearchField
          busy={itemsQuery.isFetching}
          committedValue={viewState.q}
          label="Поиск по каталогу"
          onCommit={updateSearch}
          placeholder="Модель, PN, производитель, серийный номер…"
        />
      </header>

      <div className="catalog-page__body">
        {authQuery.data?.user.role === "ADMIN" ? (
          <div className="admin-create-row">
            <Link className="button button--dark" state={{ from: returnTo }} to="/catalog/new">
              + Новая позиция
            </Link>
          </div>
        ) : null}
        {searchActive ? (
          <section aria-labelledby="global-search-title" className="catalog-section">
            <div className="section-heading">
              <div>
                <span className="section-kicker">Результаты поиска</span>
                <h2 id="global-search-title">«{viewState.q}»</h2>
              </div>
              {!itemsQuery.isPending && !itemsQuery.isError ? (
                <span className="result-count">{itemsQuery.total}</span>
              ) : null}
            </div>

            {itemsQuery.isPending ? <CatalogListSkeleton /> : null}
            {itemsQuery.isError ? (
              <CatalogErrorState onRetry={() => void itemsQuery.refetch()} />
            ) : null}
            {!itemsQuery.isPending && !itemsQuery.isError && itemsQuery.items.length === 0 ? (
              <CatalogEmptyState title="Ничего не найдено">
                Проверьте запрос или попробуйте другую модель, PN или серийный номер.
              </CatalogEmptyState>
            ) : null}
            {itemsQuery.items.length > 0 ? (
              <>
                {itemsQuery.isFetching && !itemsQuery.isFetchingNextPage ? (
                  <p className="background-status" role="status">Обновляем результаты…</p>
                ) : null}
                <EquipmentList items={itemsQuery.items} returnTo={returnTo} />
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
        ) : (
          <section aria-labelledby="category-list-title" className="catalog-section">
            <div className="section-heading section-heading--compact">
              <div>
                <span className="section-kicker">По типу оборудования</span>
                <h2 id="category-list-title">Категории</h2>
              </div>
              {categoriesQuery.data ? (
                <span className="result-count">{categoriesQuery.data.length}</span>
              ) : null}
            </div>

            {categoriesQuery.isPending ? (
              <div className="category-grid category-grid--loading" aria-label="Загрузка категорий">
                {Array.from({ length: 4 }, (_, index) => (
                  <div className="category-tile category-tile--skeleton" key={index} />
                ))}
              </div>
            ) : null}
            {categoriesQuery.isError ? (
              <CatalogErrorState
                title="Не удалось загрузить категории"
                onRetry={() => void categoriesQuery.refetch()}
              />
            ) : null}
            {categoriesQuery.data?.length === 0 ? (
              <CatalogEmptyState title="Категорий пока нет">
                Каталог ещё не настроен. Обратитесь к администратору.
              </CatalogEmptyState>
            ) : null}
            {categoriesQuery.data && categoriesQuery.data.length > 0 ? (
              <div className="category-grid">
                {[...categoriesQuery.data]
                  .sort((left, right) => left.sort_order - right.sort_order)
                  .map((category, index) => (
                    <Link
                      className="category-tile"
                      key={category.id}
                      to={`/catalog/${encodeURIComponent(category.key)}`}
                    >
                      <span className="category-tile__index">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <span className="category-tile__glyph" aria-hidden="true">
                        {category.display_name.slice(0, 2).toLocaleUpperCase("ru")}
                      </span>
                      <strong>{category.display_name}</strong>
                      {category.description ? <p>{category.description}</p> : null}
                      <span className="category-tile__mode">
                        {category.default_accounting_mode === "SERIAL" ? "Серийный" : "Количество"}
                      </span>
                      <i aria-hidden="true">↗</i>
                    </Link>
                  ))}
              </div>
            ) : null}
          </section>
        )}
      </div>
    </main>
  );
}
