import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  getCatalogCategories,
} from "../../shared/api/catalog";
import {
  getLocations,
  inventoryRequest,
  movementLabels,
  type Movement,
  type MovementCursorPage,
} from "../../shared/api/inventory";
import { SpikatelBrand } from "../../shared/brand/SpikatelBrand";
import { TelegramFullscreenButton } from "../../shared/telegram/TelegramFullscreenButton";
import "../../features/inventory/inventory.css";

const PAGE_SIZE = 30;

export function MovementsPage() {
  const [period, setPeriod] = useState("3m");
  const [actor, setActor] = useState("");
  const [equipment, setEquipment] = useState("");
  const [location, setLocation] = useState("");
  const [movementType, setMovementType] = useState("");
  const [cursorStack, setCursorStack] = useState<
    Array<{ before: number | null; snapshot?: string }>
  >([{ before: null }]);

  const cursor = cursorStack[cursorStack.length - 1];

  const hierarchy = useQuery({
    staleTime: 5 * 60_000,
    queryKey: ["catalog", "categories"],
    queryFn: ({ signal }) =>
      getCatalogCategories(signal),
  });

  const locations = useQuery({
    queryKey: ["inventory", "locations"],
    queryFn: ({ signal }) =>
      getLocations(signal),
  });

  const actors = useQuery({
    queryKey: ["inventory", "actors"],
    queryFn: ({ signal }) =>
      inventoryRequest<
        Array<{ id: string; name: string }>
      >(
        "/api/inventory/movement-actors",
        undefined,
        "GET",
        signal,
      ),
  });

  const params = new URLSearchParams({
    period,
    limit: String(PAGE_SIZE),
  });

  if (cursor.before !== null) {
    params.set(
      "before_journal_seq",
      String(cursor.before),
    );
  }

  if (cursor.snapshot) {
    params.set("snapshot_at", cursor.snapshot);
  }

  if (actor) {
    params.set("actor_user_id", actor);
  }

  if (equipment) {
    params.set(
      "category",
      equipment === "long-range"
        ? "transceivers"
        : equipment,
    );
  }

  if (equipment === "long-range") {
    params.set("long_range", "true");
  }

  if (location) {
    params.set("location_id", location);
  }

  if (movementType) {
    params.set(
      "movement_type",
      movementType,
    );
  }

  const history = useQuery({
    queryKey: [
      "inventory",
      "movements",
      "feed",
      params.toString(),
    ],
    queryFn: ({ signal }) =>
      inventoryRequest<
        MovementCursorPage<Movement>
      >(
        `/api/inventory/movements/feed?${params}`,
        undefined,
        "GET",
        signal,
      ),
  });

  const changeFilter = (
    setter: (value: string) => void,
    value: string,
  ) => {
    setter(value);
    setCursorStack([{ before: null }]);
  };

  const goBack = () => {
    setCursorStack((current) =>
      current.length > 1
        ? current.slice(0, -1)
        : current,
    );
  };

  const goNext = () => {
    const next =
      history.data?.next_before_journal_seq;

    if (next === null || next === undefined) {
      return;
    }

    setCursorStack((current) => [
      ...current.map((entry) => ({
        ...entry, snapshot: entry.snapshot ?? history.data?.snapshot_at,
      })),
      { before: next, snapshot: history.data?.snapshot_at },
    ]);
  };

  return (
    <main className="catalog-page">
      <header className="category-header warehouse-page-header">
        <div className="page-toolbar page-toolbar--brand">
          <SpikatelBrand
            inverse
            title="Инвентаризация ЦОД"
          />
          <TelegramFullscreenButton />
        </div>

        <div className="warehouse-page-header__title">
          <span className="section-kicker">
            Складской журнал
          </span>
          <h1>Движения</h1>
        </div>
      </header>

      <div className="catalog-page__body">
        <div className="history-filters">
          <label>
            Период
            <select
              value={period}
              onChange={(event) =>
                changeFilter(
                  setPeriod,
                  event.target.value,
                )
              }
            >
              {[
                ["7d", "7 дней"],
                ["30d", "30 дней"],
                ["3m", "3 месяца"],
                ["year", "Год"],
                ["all", "Всё время"],
              ].map(([key, label]) => (
                <option
                  key={key}
                  value={key}
                >
                  {label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Тип движения
            <select
              value={movementType}
              onChange={(event) =>
                changeFilter(
                  setMovementType,
                  event.target.value,
                )
              }
            >
              <option value="">
                Все типы
              </option>
              {Object.entries(
                movementLabels,
              ).map(([key, label]) => (
                <option
                  key={key}
                  value={key}
                >
                  {label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Сотрудник
            <select
              value={actor}
              onChange={(event) =>
                changeFilter(
                  setActor,
                  event.target.value,
                )
              }
            >
              <option value="">
                Все доступные
              </option>
              {actors.data?.map((item) => (
                <option
                  key={item.id}
                  value={item.id}
                >
                  {item.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            Оборудование
            <select
              value={equipment}
              onChange={(event) =>
                changeFilter(
                  setEquipment,
                  event.target.value,
                )
              }
            >
              <option value="">
                Всё оборудование
              </option>

              {hierarchy.data
                ?.filter(
                  (item) =>
                    item.parent_id === null,
                )
                .map((family) => (
                  <optgroup
                    label={family.display_name}
                    key={family.id}
                  >
                    <option value={family.key}>
                      {family.display_name} — всё
                    </option>

                    {hierarchy.data
                      .filter(
                        (item) =>
                          item.parent_id
                          === family.id,
                      )
                      .map((leaf) => (
                        <option
                          value={leaf.key}
                          key={leaf.id}
                        >
                          {leaf.display_name}
                        </option>
                      ))}

                    {family.key
                    === "transceivers" ? (
                      <option value="long-range">
                        Дальние
                      </option>
                    ) : null}
                  </optgroup>
                ))}
            </select>
          </label>

          <label>
            Место хранения
            <select
              value={location}
              onChange={(event) =>
                changeFilter(
                  setLocation,
                  event.target.value,
                )
              }
            >
              <option value="">
                Все места
              </option>
              {locations.data?.map((item) => (
                <option
                  key={item.id}
                  value={item.id}
                >
                  {item.name}
                  {item.status === "ARCHIVED"
                    ? " (архив)"
                    : ""}
                </option>
              ))}
            </select>
          </label>
        </div>

        {actors.isError
        || hierarchy.isError
        || locations.isError ? (
          <p role="alert">
            Не удалось загрузить часть фильтров.{" "}
            <button
              onClick={() => {
                void actors.refetch();
                void hierarchy.refetch();
                void locations.refetch();
              }}
            >
              Повторить
            </button>
          </p>
        ) : null}

        {history.isPending ? (
          <p role="status">
            Загружаем журнал…
          </p>
        ) : null}

        {history.isError ? (
          <p role="alert">
            Не удалось загрузить журнал.{" "}
            <button
              onClick={() =>
                void history.refetch()
              }
            >
              Повторить
            </button>
          </p>
        ) : null}

        {history.data?.items.length === 0 ? (
          <p>
            За выбранный период движений нет.
          </p>
        ) : null}

        {history.data?.items.map(
          (movement) => (
            <article
              className="movement-entry"
              key={movement.id}
            >
              <header>
                <span>
                  № {movement.journal_seq}
                </span>
                <time
                  dateTime={
                    movement.occurred_at
                  }
                >
                  {new Date(
                    movement.occurred_at,
                  ).toLocaleString("ru-RU")}
                </time>
              </header>

              <p>
                <strong>
                  {
                    movement.actor_display_name_snapshot
                  }
                </strong>
                {" · "}
                {
                  movementLabels[
                    movement.movement_type
                  ]
                }
              </p>

              <ul>
                {movement.lines.map(
                  (line) => (
                    <li key={line.id}>
                      {
                        line.item_name_snapshot
                      }
                      {" — "}
                      <strong>
                        {line.quantity} шт.
                      </strong>
                    </li>
                  ),
                )}
              </ul>

              <p>
                {movement.source_location_name_snapshot
                  ? `Из: ${movement.source_location_name_snapshot}`
                  : ""}
                {movement.source_location_name_snapshot
                && movement.destination_location_name_snapshot
                  ? " → "
                  : ""}
                {movement.destination_location_name_snapshot
                  ? `В: ${movement.destination_location_name_snapshot}`
                  : ""}
              </p>
            </article>
          ),
        )}

        <div className="warehouse-actions">
          {cursorStack.length > 1 ? (
            <button
              className="button"
              onClick={goBack}
            >
              Назад
            </button>
          ) : null}

          {history.data
            ?.next_before_journal_seq
          !== null
          && history.data
            ?.next_before_journal_seq
          !== undefined ? (
            <button
              className="button"
              onClick={goNext}
            >
              Следующая страница
            </button>
          ) : null}
        </div>
      </div>
    </main>
  );
}
