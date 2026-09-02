import { useQuery } from "@tanstack/react-query";
import {
  useLocation,
  useParams,
} from "react-router-dom";

import {
  getCatalogCategory,
  getCatalogItem,
  type InventorySummary,
} from "../../shared/api/catalog";
import {
  CatalogErrorState,
  CatalogListSkeleton,
} from "../../features/catalog/CatalogState";
import {
  formatAccountingMode,
  formatAttributeValue,
  formatItemStatus,
  safeExternalUrl,
} from "../../features/catalog/format";
import { useInternalBackNavigation } from "../../features/navigation/useTelegramNavigation";

type ItemNavigationState = {
  from?: unknown;
  inventory?: unknown;
};

function inventoryFromState(state: unknown): InventorySummary | null {
  if (state === null || typeof state !== "object") {
    return null;
  }
  const inventory = (state as ItemNavigationState).inventory;
  if (inventory === null || typeof inventory !== "object") {
    return null;
  }
  const candidate = inventory as Partial<InventorySummary>;
  if (
    typeof candidate.available_count !== "number"
    || typeof candidate.custody_count !== "number"
    || typeof candidate.total_count !== "number"
    || candidate.available_count < 0
    || candidate.custody_count < 0
    || candidate.total_count < 0
  ) {
    return null;
  }
  return candidate as InventorySummary;
}

export function ItemDetailPage() {
  const { itemId = "" } = useParams();
  const location = useLocation();
  const inventory = inventoryFromState(location.state);
  const navigateBack = useInternalBackNavigation();
  const itemQuery = useQuery({
    queryKey: ["catalog", "item", itemId],
    queryFn: ({ signal }) => getCatalogItem(itemId, signal),
    enabled: itemId !== "",
  });
  const categoryKey = itemQuery.data?.category.key;
  const categoryQuery = useQuery({
    queryKey: ["catalog", "category", categoryKey],
    queryFn: ({ signal }) => getCatalogCategory(categoryKey ?? "", signal),
    enabled: categoryKey !== undefined,
    staleTime: 5 * 60_000,
  });

  if (itemQuery.isPending) {
    return (
      <main className="catalog-page detail-page">
        <header className="detail-header detail-header--loading">
          <button aria-label="Назад" className="icon-button icon-button--light" onClick={navigateBack} type="button">←</button>
          <span>Spikatel Inventory</span>
        </header>
        <div className="catalog-page__body"><CatalogListSkeleton count={2} /></div>
      </main>
    );
  }

  if (itemQuery.isError || itemQuery.data === undefined) {
    return (
      <main className="catalog-page detail-page">
        <header className="detail-header">
          <button aria-label="Назад" className="icon-button icon-button--light" onClick={navigateBack} type="button">←</button>
          <span>Карточка оборудования</span>
        </header>
        <div className="catalog-page__body">
          <CatalogErrorState
            title="Не удалось загрузить карточку"
            onRetry={() => void itemQuery.refetch()}
          />
        </div>
      </main>
    );
  }

  const item = itemQuery.data;
  const visibleAttributes = (categoryQuery.data?.attributes ?? [])
    .filter(
      (attribute) =>
        attribute.detail_visible && item.attributes[attribute.key] !== undefined,
    )
    .sort((left, right) => left.sort_order - right.sort_order);
  const datasheetUrl = safeExternalUrl(item.datasheet_url);

  return (
    <main className="catalog-page detail-page">
      <header className="detail-header">
        <button aria-label="Назад" className="icon-button icon-button--light" onClick={navigateBack} type="button">←</button>
        <span>Карточка оборудования</span>
        <span className={item.status === "ARCHIVED" ? "status-badge status-badge--archived" : "status-badge"}>
          {item.status === "ARCHIVED" ? "Архив" : "Активно"}
        </span>
      </header>

      <div className="detail-hero">
        <div className="detail-visual" aria-hidden="true">
          <span>{item.category.display_name.slice(0, 2).toLocaleUpperCase("ru")}</span>
          <small>{item.category.key}</small>
        </div>
        <div className="detail-identity">
          <span className="section-kicker">{item.category.display_name}</span>
          <p className="detail-identity__maker">{item.manufacturer?.name ?? "Без производителя"}</p>
          <h1>{item.model?.trim() || item.name}</h1>
          {item.model !== null && item.name !== item.model ? <p>{item.name}</p> : null}
          {item.manufacturer_part_number ? (
            <span className="detail-identity__pn">PN {item.manufacturer_part_number}</span>
          ) : null}
        </div>
      </div>

      <div className="catalog-page__body detail-body">
        {inventory ? (
          <section aria-labelledby="stock-title" className="detail-panel detail-panel--stock">
            <div className="detail-panel__heading">
              <div>
                <span className="section-kicker">Текущий остаток</span>
                <h2 id="stock-title">Наличие</h2>
              </div>
              <small>Из списка каталога</small>
            </div>
            <dl className="stock-strip stock-strip--detail">
              <div className={inventory.available_count > 0 ? "stock-strip__available" : "stock-strip__zero"}>
                <dt>Доступно</dt>
                <dd>{inventory.available_count}</dd>
              </div>
              <div>
                <dt>У пользователей</dt>
                <dd>{inventory.custody_count}</dd>
              </div>
              <div>
                <dt>Всего активно</dt>
                <dd>{inventory.total_count}</dd>
              </div>
            </dl>
          </section>
        ) : null}

        <section aria-labelledby="identity-title" className="detail-panel">
          <div className="detail-panel__heading">
            <div>
              <span className="section-kicker">Учётные данные</span>
              <h2 id="identity-title">Идентификация</h2>
            </div>
          </div>
          <dl className="detail-list">
            <div><dt>Категория</dt><dd>{item.category.display_name}</dd></div>
            <div><dt>Производитель</dt><dd>{item.manufacturer?.name ?? "Не указан"}</dd></div>
            <div><dt>Название</dt><dd>{item.name}</dd></div>
            {item.model ? <div><dt>Модель</dt><dd>{item.model}</dd></div> : null}
            {item.manufacturer_part_number ? <div><dt>Part number</dt><dd>{item.manufacturer_part_number}</dd></div> : null}
            {item.internal_code ? <div><dt>Внутренний код</dt><dd>{item.internal_code}</dd></div> : null}
            <div><dt>Способ учёта</dt><dd>{formatAccountingMode(item.accounting_mode)}</dd></div>
            <div><dt>Статус</dt><dd>{formatItemStatus(item.status)}</dd></div>
          </dl>
        </section>

        {categoryQuery.isPending ? (
          <section className="detail-panel detail-panel--loading" aria-label="Загрузка характеристик">
            <span /><span /><span />
          </section>
        ) : null}
        {categoryQuery.isError ? (
          <section className="detail-panel">
            <CatalogErrorState
              title="Не удалось загрузить характеристики"
              onRetry={() => void categoryQuery.refetch()}
            />
          </section>
        ) : null}
        {!categoryQuery.isPending && !categoryQuery.isError && visibleAttributes.length > 0 ? (
          <section aria-labelledby="attributes-title" className="detail-panel">
            <div className="detail-panel__heading">
              <div>
                <span className="section-kicker">Параметры</span>
                <h2 id="attributes-title">Характеристики</h2>
              </div>
              <span className="result-count">{visibleAttributes.length}</span>
            </div>
            <dl className="detail-list detail-list--attributes">
              {visibleAttributes.map((attribute) => (
                <div key={attribute.key}>
                  <dt>{attribute.label}</dt>
                  <dd>{formatAttributeValue(item.attributes[attribute.key], attribute.unit)}</dd>
                </div>
              ))}
            </dl>
          </section>
        ) : null}

        {item.description || item.comment ? (
          <section aria-labelledby="notes-title" className="detail-panel">
            <div className="detail-panel__heading">
              <div><span className="section-kicker">Контекст</span><h2 id="notes-title">Описание</h2></div>
            </div>
            <div className="detail-copy">
              {item.description ? <p>{item.description}</p> : null}
              {item.comment ? <aside><strong>Комментарий</strong><p>{item.comment}</p></aside> : null}
            </div>
          </section>
        ) : null}

        {item.technical_data_source || datasheetUrl ? (
          <section aria-labelledby="sources-title" className="detail-panel">
            <div className="detail-panel__heading">
              <div><span className="section-kicker">Документация</span><h2 id="sources-title">Источники</h2></div>
            </div>
            {item.technical_data_source ? (
              <p className="technical-source">{item.technical_data_source}</p>
            ) : null}
            {datasheetUrl ? (
              <a
                className="button button--accent detail-datasheet"
                href={datasheetUrl}
                rel="noopener noreferrer"
                target="_blank"
              >
                Открыть datasheet <span aria-hidden="true">↗</span>
              </a>
            ) : null}
          </section>
        ) : null}
      </div>
    </main>
  );
}
