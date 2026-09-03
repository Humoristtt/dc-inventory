import { useInfiniteQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useAuthState } from "../../features/auth/useAuthState";
import {
  CatalogEmptyState,
  CatalogErrorState,
  CatalogListSkeleton,
} from "../../features/catalog/CatalogState";
import {
  getMyEquipmentPage,
  type InventoryPage,
} from "../../shared/api/inventory";
import { SpikatelBrand } from "../../shared/brand/SpikatelBrand";
import "../../features/inventory/inventory.css";

const HOLDINGS_PAGE_SIZE = 20;

function nextOffset<T>(
  lastPage: InventoryPage<T>,
): number | undefined {
  if (lastPage.items.length === 0) {
    return undefined;
  }

  const next = lastPage.offset + lastPage.items.length;
  return next < lastPage.total ? next : undefined;
}

export function MyEquipmentPage() {
  const authQuery = useAuthState();
  const userId = authQuery.data?.user.id;

  const mineQuery = useInfiniteQuery({
    queryKey: ["inventory", "mine", userId],
    queryFn: ({ pageParam, signal }) => getMyEquipmentPage(
      {
        limit: HOLDINGS_PAGE_SIZE,
        offset: pageParam,
      },
      signal,
    ),
    initialPageParam: 0,
    getNextPageParam: nextOffset,
    enabled: userId !== undefined,
  });

  const pending = authQuery.isPending
    || (userId !== undefined && mineQuery.isPending);

  const failed = authQuery.isError || mineQuery.isError;

  const holdings = mineQuery.data?.pages.flatMap(
    (page) => page.items,
  ) ?? [];

  const total = mineQuery.data?.pages[0]?.total ?? 0;

  return (
    <main className="mine-page">
      <header className="mine-header">
        <SpikatelBrand inverse subtitle="Персональный учёт" />
        <div>
          <span className="section-kicker">
            Текущая ответственность
          </span>
          <h1>Моё оборудование</h1>
          <p>
            Только позиции, которые сейчас числятся за вами.
          </p>
        </div>
      </header>

      <div className="mine-page__body">
        {pending ? <CatalogListSkeleton count={3} /> : null}

        {failed ? (
          <CatalogErrorState
            title="Не удалось загрузить оборудование"
            onRetry={() => void mineQuery.refetch()}
          />
        ) : null}

        {!pending && !failed && total === 0 ? (
          <CatalogEmptyState title="У вас пока нет оборудования">
            Выданные позиции появятся здесь автоматически.
          </CatalogEmptyState>
        ) : null}

        {!pending && !failed && total > 0 ? (
          <section
            aria-labelledby="holdings-title"
            className="holdings-section"
          >
            <div className="section-heading section-heading--compact">
              <div>
                <span className="section-kicker">На руках</span>
                <h2 id="holdings-title">Позиции</h2>
              </div>
              <span className="result-count">{total}</span>
            </div>

            <div className="holdings-list">
              {holdings.map((holding) => (
                <Link
                  className="holding-card"
                  key={holding.item_id}
                  to={`/catalog/items/${encodeURIComponent(holding.item_id)}`}
                >
                  <div className="holding-card__heading">
                    <div>
                      <span>
                        {holding.accounting_mode === "SERIAL"
                          ? "Серийный учёт"
                          : "Количество"}
                      </span>
                      <h3>{holding.item_name}</h3>
                    </div>

                    <b>
                      {holding.accounting_mode === "SERIAL"
                        ? `${holding.serial_count} шт.`
                        : `${holding.quantity} шт.`}
                    </b>
                  </div>

                  {holding.accounting_mode === "SERIAL" ? (
                    <>
                      <ul>
                        {holding.serial_preview.map((unit) => (
                          <li key={unit.id}>
                            <strong>SN {unit.serial_number}</strong>
                            {unit.wwn ? (
                              <span>WWN {unit.wwn}</span>
                            ) : null}
                          </li>
                        ))}
                      </ul>

                      {holding.serial_count > holding.serial_preview.length ? (
                        <p>
                          Показано {holding.serial_preview.length} из{" "}
                          <strong>{holding.serial_count}</strong>.
                          Полный список — в карточке позиции.
                        </p>
                      ) : null}
                    </>
                  ) : (
                    <p>
                      Количество в вашей ответственности:{" "}
                      <strong>{holding.quantity}</strong>
                    </p>
                  )}

                  <span className="holding-card__link">
                    Открыть карточку →
                  </span>
                </Link>
              ))}
            </div>

            {mineQuery.hasNextPage ? (
              <button
                className="button button--secondary"
                disabled={mineQuery.isFetchingNextPage}
                onClick={() => void mineQuery.fetchNextPage()}
                type="button"
              >
                {mineQuery.isFetchingNextPage
                  ? "Загрузка…"
                  : "Показать ещё"}
              </button>
            ) : null}
          </section>
        ) : null}
      </div>
    </main>
  );
}
