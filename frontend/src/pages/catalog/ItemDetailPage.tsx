import { SpikatelBrand } from "../../shared/brand/SpikatelBrand";
import { TelegramFullscreenButton } from "../../shared/telegram/TelegramFullscreenButton";
import { useTelegramWebApp } from "../../shared/telegram/useTelegramWebApp";
import { useQuery } from "@tanstack/react-query";
import {
  useLocation,
  useParams,
} from "react-router-dom";

import {
  getCatalogCategory,
  getCatalogItem,
  type CatalogItem,
} from "../../shared/api/catalog";
import {
  CatalogErrorState,
  CatalogListSkeleton,
} from "../../features/catalog/CatalogState";
import { AdminItemActions } from "../../features/catalog/AdminItemActions";
import { ItemInventoryPanel } from "../../features/inventory/ItemInventoryPanel";
import {
  formatCatalogAttributeValue,
  formatItemStatus,
} from "../../features/catalog/format";
import { useInternalBackNavigation } from "../../features/navigation/useTelegramNavigation";

export function ItemDetailPage() {
  const webApp = useTelegramWebApp();
  const location = useLocation();
  const { itemId = "" } = useParams();
  const navigateBack = useInternalBackNavigation();
  const previewItem = (
    location.state as { item?: CatalogItem } | null
  )?.item;
  const telegramOwnsBack = webApp?.BackButton !== undefined;
  const itemQuery = useQuery({
    queryKey: ["catalog", "item", itemId],
    queryFn: ({ signal }) => getCatalogItem(itemId, signal),
    enabled: itemId !== "",
    placeholderData:
      previewItem?.id === itemId ? previewItem : undefined,
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
          <div className="page-toolbar page-toolbar--brand">
            <SpikatelBrand inverse title="Инвентаризация ЦОД" />
            <TelegramFullscreenButton />
          </div>
          {!telegramOwnsBack ? (
            <button
              aria-label="Назад"
              className="icon-button icon-button--light"
              onClick={navigateBack}
              type="button"
            >
              ←
            </button>
          ) : null}
        </header>
        <div className="catalog-page__body"><CatalogListSkeleton count={2} /></div>
      </main>
    );
  }

  if (itemQuery.isError || itemQuery.data === undefined) {
    return (
      <main className="catalog-page detail-page">
        <header className="detail-header">
          <div className="page-toolbar page-toolbar--brand">
            <SpikatelBrand inverse title="Инвентаризация ЦОД" />
            <TelegramFullscreenButton />
          </div>
          <div className="detail-header__row detail-header__row--title">
            {!telegramOwnsBack ? (
              <button
                aria-label="Назад"
                className="icon-button icon-button--light"
                onClick={navigateBack}
                type="button"
              >
                ←
              </button>
            ) : null}
            <div className="detail-header__title">
              <span className="section-kicker">Каталог</span>
              <strong>Карточка оборудования</strong>
            </div>
          </div>
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

  return (
    <main className="catalog-page detail-page">
      <header className="detail-header">
      <div className="page-toolbar page-toolbar--brand">
        <SpikatelBrand inverse title="Инвентаризация ЦОД" />
        <TelegramFullscreenButton />
      </div>
      <div className="detail-header__row detail-header__row--title">
        {!telegramOwnsBack ? (
          <button
            aria-label="Назад"
            className="icon-button icon-button--light"
            onClick={navigateBack}
            type="button"
          >
            ←
          </button>
        ) : null}
        <div className="detail-header__title">
          <span className="section-kicker">Каталог</span>
          <strong>Карточка оборудования</strong>
        </div>
        <div className="detail-header__actions">
          <span
            className={
              item.status === "ARCHIVED"
                ? "status-badge status-badge--archived"
                : "status-badge"
            }
          >
            {item.status === "ARCHIVED" ? "Архив" : "Активно"}
          </span>
        </div>
      </div>
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
        </div>
      </div>

      <div className="catalog-page__body detail-body">
        <ItemInventoryPanel itemId={item.id} archived={item.status === "ARCHIVED"} />

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
                  <dd>{formatCatalogAttributeValue(attribute.key, item.attributes[attribute.key], attribute.unit)}</dd>
                </div>
              ))}
            </dl>
          </section>
        ) : null}

        <AdminItemActions item={item} />
      </div>
    </main>
  );
}
