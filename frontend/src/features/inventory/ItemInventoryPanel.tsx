import {
  useInfiniteQuery,
  useQuery,
} from "@tanstack/react-query";

import type {
  AccountingMode,
} from "../../shared/api/catalog";
import {
  getInventoryStockPage,
  getInventorySummary,
  getInventoryUnitsPage,
  type InventoryPage,
} from "../../shared/api/inventory";
import { CatalogErrorState } from "../catalog/CatalogState";
import "./inventory.css";

type ItemInventoryPanelProps = {
  itemId: string;
  mode: AccountingMode;
};

const DETAIL_PAGE_SIZE = 50;

function nextOffset<T>(
  lastPage: InventoryPage<T>,
): number | undefined {
  if (lastPage.items.length === 0) {
    return undefined;
  }

  const next = lastPage.offset + lastPage.items.length;
  return next < lastPage.total ? next : undefined;
}

export function ItemInventoryPanel({
  itemId,
  mode,
}: ItemInventoryPanelProps) {
  const summaryQuery = useQuery({
    queryKey: ["inventory", "summary", "item", itemId],
    queryFn: ({ signal }) => getInventorySummary(itemId, signal),
  });

  const quantityQuery = useInfiniteQuery({
    queryKey: ["inventory", "stock", "item", itemId],
    queryFn: ({ pageParam, signal }) => getInventoryStockPage(
      { itemId },
      { limit: DETAIL_PAGE_SIZE, offset: pageParam },
      signal,
    ),
    initialPageParam: 0,
    getNextPageParam: nextOffset,
    enabled: mode === "QUANTITY",
  });

  const storedQuery = useInfiniteQuery({
    queryKey: ["inventory", "units", "item", itemId, "STORED"],
    queryFn: ({ pageParam, signal }) => getInventoryUnitsPage(
      { itemId, state: "STORED" },
      { limit: DETAIL_PAGE_SIZE, offset: pageParam },
      signal,
    ),
    initialPageParam: 0,
    getNextPageParam: nextOffset,
    enabled: mode === "SERIAL",
  });

  const issuedQuery = useInfiniteQuery({
    queryKey: ["inventory", "units", "item", itemId, "ISSUED"],
    queryFn: ({ pageParam, signal }) => getInventoryUnitsPage(
      { itemId, state: "ISSUED" },
      { limit: DETAIL_PAGE_SIZE, offset: pageParam },
      signal,
    ),
    initialPageParam: 0,
    getNextPageParam: nextOffset,
    enabled: mode === "SERIAL",
  });

  const pending = summaryQuery.isPending || (
    mode === "QUANTITY"
      ? quantityQuery.isPending
      : storedQuery.isPending || issuedQuery.isPending
  );

  const failed = summaryQuery.isError || (
    mode === "QUANTITY"
      ? quantityQuery.isError
      : storedQuery.isError || issuedQuery.isError
  );

  const retry = () => {
    void summaryQuery.refetch();

    if (mode === "QUANTITY") {
      void quantityQuery.refetch();
      return;
    }

    void storedQuery.refetch();
    void issuedQuery.refetch();
  };

  if (pending) {
    return (
      <section
        aria-label="Загрузка складских позиций"
        className="detail-panel detail-panel--loading"
      >
        <span /><span />
      </section>
    );
  }

  if (failed || summaryQuery.data === undefined) {
    return (
      <section className="detail-panel">
        <CatalogErrorState
          title="Не удалось загрузить остатки"
          onRetry={retry}
        />
      </section>
    );
  }

  const quantityRows = quantityQuery.data?.pages.flatMap(
    (page) => page.items,
  ) ?? [];

  const locationRows = mode === "QUANTITY"
    ? quantityRows.filter((row) => row.location !== null)
    : storedQuery.data?.pages.flatMap((page) => page.items) ?? [];

  const holderRows = mode === "QUANTITY"
    ? quantityRows.filter((row) => row.holder !== null)
    : issuedQuery.data?.pages.flatMap((page) => page.items) ?? [];

  const resolvedSummary = summaryQuery.data;

  return (
    <section
      aria-labelledby="stock-title"
      className="detail-panel detail-panel--stock"
    >
      <div className="detail-panel__heading">
        <div>
          <span className="section-kicker">Текущая проекция</span>
          <h2 id="stock-title">Наличие и хранение</h2>
        </div>
        <small>
          {mode === "QUANTITY" ? "Количество" : "Серийный учёт"}
        </small>
      </div>

      <dl className="stock-strip stock-strip--detail">
        <div
          className={
            resolvedSummary.available_count > 0
              ? "stock-strip__available"
              : "stock-strip__zero"
          }
        >
          <dt>Доступно</dt>
          <dd>{resolvedSummary.available_count}</dd>
        </div>
        <div>
          <dt>У пользователей</dt>
          <dd>{resolvedSummary.custody_count}</dd>
        </div>
        <div>
          <dt>Всего активно</dt>
          <dd>{resolvedSummary.total_count}</dd>
        </div>
      </dl>

      {resolvedSummary.total_count === 0 ? (
        <div className="inventory-empty">
          <strong>Текущих остатков нет</strong>
          <p>
            Позиция ещё не размещена на складе и не числится за сотрудниками.
          </p>
        </div>
      ) : (
        <div className="inventory-columns">
          <div>
            <h3>По локациям</h3>

            {locationRows.length === 0 ? (
              <p className="inventory-list-empty">
                {resolvedSummary.available_count > 0
                  ? "Остатки есть — загрузите следующие позиции"
                  : "На складе нет"}
              </p>
            ) : (
              <ul className="position-list">
                {locationRows.map((row) => (
                  <li key={row.id}>
                    <div>
                      <strong>
                        {row.location?.code ?? "Локация"}
                      </strong>
                      <span>{row.location?.name}</span>

                      {"serial_number" in row
                        && row.serial_number !== null ? (
                          <small>
                            SN {row.serial_number}
                            {row.wwn ? ` · WWN ${row.wwn}` : ""}
                          </small>
                        ) : null}
                    </div>

                    <b>
                      {"quantity" in row
                        ? row.quantity
                        : "1 шт."}
                    </b>
                  </li>
                ))}
              </ul>
            )}

            {mode === "SERIAL" && storedQuery.hasNextPage ? (
              <button
                className="button button--secondary"
                disabled={storedQuery.isFetchingNextPage}
                onClick={() => void storedQuery.fetchNextPage()}
                type="button"
              >
                {storedQuery.isFetchingNextPage
                  ? "Загрузка…"
                  : "Показать ещё на складе"}
              </button>
            ) : null}
          </div>

          <div>
            <h3>У сотрудников</h3>

            {holderRows.length === 0 ? (
              <p className="inventory-list-empty">
                {resolvedSummary.custody_count > 0
                  ? "Выданные позиции есть — загрузите следующие позиции"
                  : "На руках нет"}
              </p>
            ) : (
              <ul className="position-list">
                {holderRows.map((row) => (
                  <li key={row.id}>
                    <div>
                      <strong>
                        {row.holder?.display_name ?? "Сотрудник"}
                      </strong>

                      {"serial_number" in row
                        && row.serial_number !== null ? (
                          <small>
                            SN {row.serial_number}
                            {row.wwn ? ` · WWN ${row.wwn}` : ""}
                          </small>
                        ) : null}
                    </div>

                    <b>
                      {"quantity" in row
                        ? row.quantity
                        : "1 шт."}
                    </b>
                  </li>
                ))}
              </ul>
            )}

            {mode === "SERIAL" && issuedQuery.hasNextPage ? (
              <button
                className="button button--secondary"
                disabled={issuedQuery.isFetchingNextPage}
                onClick={() => void issuedQuery.fetchNextPage()}
                type="button"
              >
                {issuedQuery.isFetchingNextPage
                  ? "Загрузка…"
                  : "Показать ещё у сотрудников"}
              </button>
            ) : null}
          </div>
        </div>
      )}

      {mode === "QUANTITY" && quantityQuery.hasNextPage ? (
        <button
          className="button button--secondary"
          disabled={quantityQuery.isFetchingNextPage}
          onClick={() => void quantityQuery.fetchNextPage()}
          type="button"
        >
          {quantityQuery.isFetchingNextPage
            ? "Загрузка…"
            : "Показать ещё позиции"}
        </button>
      ) : null}
    </section>
  );
}
