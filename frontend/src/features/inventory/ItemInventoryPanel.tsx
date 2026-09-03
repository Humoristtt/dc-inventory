import { useQuery } from "@tanstack/react-query";

import type {
  AccountingMode,
} from "../../shared/api/catalog";
import {
  getInventoryStock,
  getInventoryUnits,
} from "../../shared/api/inventory";
import { CatalogErrorState } from "../catalog/CatalogState";
import "./inventory.css";

type ItemInventoryPanelProps = {
  itemId: string;
  mode: AccountingMode;
};

export function ItemInventoryPanel({
  itemId,
  mode,
}: ItemInventoryPanelProps) {
  const quantityQuery = useQuery({
    queryKey: ["inventory", "stock", "item", itemId],
    queryFn: ({ signal }) => getInventoryStock({ itemId }, signal),
    enabled: mode === "QUANTITY",
  });
  const serialQuery = useQuery({
    queryKey: ["inventory", "units", "item", itemId, "current"],
    queryFn: async ({ signal }) => {
      const [stored, issued] = await Promise.all([
        getInventoryUnits({ itemId, state: "STORED" }, signal),
        getInventoryUnits({ itemId, state: "ISSUED" }, signal),
      ]);
      return { stored, issued };
    },
    enabled: mode === "SERIAL",
  });

  const pending = mode === "QUANTITY" ? quantityQuery.isPending : serialQuery.isPending;
  const failed = mode === "QUANTITY" ? quantityQuery.isError : serialQuery.isError;
  const retry = () => {
    if (mode === "QUANTITY") {
      void quantityQuery.refetch();
    } else {
      void serialQuery.refetch();
    }
  };

  if (pending) {
    return (
      <section aria-label="Загрузка складских позиций" className="detail-panel detail-panel--loading">
        <span /><span />
      </section>
    );
  }

  if (failed) {
    return (
      <section className="detail-panel">
        <CatalogErrorState title="Не удалось загрузить остатки" onRetry={retry} />
      </section>
    );
  }

  const locationRows = mode === "QUANTITY"
    ? (quantityQuery.data ?? []).filter((row) => row.location !== null)
    : serialQuery.data?.stored ?? [];
  const holderRows = mode === "QUANTITY"
    ? (quantityQuery.data ?? []).filter((row) => row.holder !== null)
    : serialQuery.data?.issued ?? [];
  const available = mode === "QUANTITY"
    ? locationRows.reduce(
      (total, row) => total + ("quantity" in row ? row.quantity : 0),
      0,
    )
    : locationRows.length;
  const custody = mode === "QUANTITY"
    ? holderRows.reduce(
      (total, row) => total + ("quantity" in row ? row.quantity : 0),
      0,
    )
    : holderRows.length;
  const resolvedSummary = {
    available_count: available,
    custody_count: custody,
    total_count: available + custody,
  };

  return (
    <section aria-labelledby="stock-title" className="detail-panel detail-panel--stock">
      <div className="detail-panel__heading">
        <div>
          <span className="section-kicker">Текущая проекция</span>
          <h2 id="stock-title">Наличие и хранение</h2>
        </div>
        <small>{mode === "QUANTITY" ? "Количество" : "Серийный учёт"}</small>
      </div>
      <dl className="stock-strip stock-strip--detail">
        <div className={resolvedSummary.available_count > 0 ? "stock-strip__available" : "stock-strip__zero"}>
          <dt>Доступно</dt><dd>{resolvedSummary.available_count}</dd>
        </div>
        <div><dt>У пользователей</dt><dd>{resolvedSummary.custody_count}</dd></div>
        <div><dt>Всего активно</dt><dd>{resolvedSummary.total_count}</dd></div>
      </dl>

      {locationRows.length === 0 && holderRows.length === 0 ? (
        <div className="inventory-empty">
          <strong>Текущих остатков нет</strong>
          <p>Позиция ещё не размещена на складе и не числится за сотрудниками.</p>
        </div>
      ) : (
        <div className="inventory-columns">
          <div>
            <h3>По локациям</h3>
            {locationRows.length === 0 ? <p className="inventory-list-empty">На складе нет</p> : (
              <ul className="position-list">
                {locationRows.map((row) => (
                  <li key={row.id}>
                    <div>
                      <strong>{row.location?.code ?? "Локация"}</strong>
                      <span>{row.location?.name}</span>
                      {"serial_number" in row ? (
                        <small>SN {row.serial_number}{row.wwn ? ` · WWN ${row.wwn}` : ""}</small>
                      ) : null}
                    </div>
                    <b>{"quantity" in row ? row.quantity : "1 шт."}</b>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3>У сотрудников</h3>
            {holderRows.length === 0 ? <p className="inventory-list-empty">На руках нет</p> : (
              <ul className="position-list">
                {holderRows.map((row) => (
                  <li key={row.id}>
                    <div>
                      <strong>{row.holder?.display_name ?? "Сотрудник"}</strong>
                      {"serial_number" in row ? (
                        <small>SN {row.serial_number}{row.wwn ? ` · WWN ${row.wwn}` : ""}</small>
                      ) : null}
                    </div>
                    <b>{"quantity" in row ? row.quantity : "1 шт."}</b>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
