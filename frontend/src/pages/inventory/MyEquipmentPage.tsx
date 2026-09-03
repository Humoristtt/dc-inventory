import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useAuthState } from "../../features/auth/useAuthState";
import {
  CatalogEmptyState,
  CatalogErrorState,
  CatalogListSkeleton,
} from "../../features/catalog/CatalogState";
import {
  getInventoryStock,
  getInventoryUnits,
  type InventoryUnit,
} from "../../shared/api/inventory";
import { SpikatelBrand } from "../../shared/brand/SpikatelBrand";
import "../../features/inventory/inventory.css";

type Holding = {
  itemId: string;
  itemName: string;
  quantity: number;
  units: InventoryUnit[];
};

export function MyEquipmentPage() {
  const authQuery = useAuthState();
  const userId = authQuery.data?.user.id;
  const quantityQuery = useQuery({
    queryKey: ["inventory", "stock", "holder", userId],
    queryFn: ({ signal }) => getInventoryStock({ holderUserId: userId }, signal),
    enabled: userId !== undefined,
  });
  const unitsQuery = useQuery({
    queryKey: ["inventory", "units", "holder", userId, "ISSUED"],
    queryFn: ({ signal }) => getInventoryUnits({ holderUserId: userId, state: "ISSUED" }, signal),
    enabled: userId !== undefined,
  });

  const pending = authQuery.isPending
    || (userId !== undefined && (quantityQuery.isPending || unitsQuery.isPending));
  const failed = authQuery.isError || quantityQuery.isError || unitsQuery.isError;
  const holdings = new Map<string, Holding>();
  for (const row of quantityQuery.data ?? []) {
    holdings.set(row.item_id, {
      itemId: row.item_id,
      itemName: row.item_name,
      quantity: row.quantity,
      units: [],
    });
  }
  for (const unit of unitsQuery.data ?? []) {
    const holding = holdings.get(unit.item_id) ?? {
      itemId: unit.item_id,
      itemName: unit.item_name,
      quantity: 0,
      units: [],
    };
    holding.units.push(unit);
    holdings.set(unit.item_id, holding);
  }
  const grouped = [...holdings.values()].sort((left, right) =>
    left.itemName.localeCompare(right.itemName, "ru"),
  );

  return (
    <main className="mine-page">
      <header className="mine-header">
        <SpikatelBrand inverse subtitle="Персональный учёт" />
        <div>
          <span className="section-kicker">Текущая ответственность</span>
          <h1>Моё оборудование</h1>
          <p>Только позиции, которые сейчас числятся за вами.</p>
        </div>
      </header>
      <div className="mine-page__body">
        {pending ? <CatalogListSkeleton count={3} /> : null}
        {failed ? (
          <CatalogErrorState
            title="Не удалось загрузить оборудование"
            onRetry={() => {
              void quantityQuery.refetch();
              void unitsQuery.refetch();
            }}
          />
        ) : null}
        {!pending && !failed && grouped.length === 0 ? (
          <CatalogEmptyState title="У вас пока нет оборудования">
            Выданные позиции появятся здесь автоматически.
          </CatalogEmptyState>
        ) : null}
        {!pending && !failed && grouped.length > 0 ? (
          <section aria-labelledby="holdings-title" className="holdings-section">
            <div className="section-heading section-heading--compact">
              <div><span className="section-kicker">На руках</span><h2 id="holdings-title">Позиции</h2></div>
              <span className="result-count">{grouped.length}</span>
            </div>
            <div className="holdings-list">
              {grouped.map((holding) => (
                <Link className="holding-card" key={holding.itemId} to={`/catalog/items/${encodeURIComponent(holding.itemId)}`}>
                  <div className="holding-card__heading">
                    <div><span>{holding.units.length > 0 ? "Серийный учёт" : "Количество"}</span><h3>{holding.itemName}</h3></div>
                    <b>{holding.units.length > 0 ? `${holding.units.length} шт.` : `${holding.quantity} шт.`}</b>
                  </div>
                  {holding.units.length > 0 ? (
                    <ul>
                      {holding.units.map((unit) => (
                        <li key={unit.id}>
                          <strong>SN {unit.serial_number}</strong>
                          {unit.wwn ? <span>WWN {unit.wwn}</span> : null}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>Количество в вашей ответственности: <strong>{holding.quantity}</strong></p>
                  )}
                  <span className="holding-card__link">Открыть карточку →</span>
                </Link>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </main>
  );
}
