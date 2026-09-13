import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";

import { useAuthState } from "../../features/auth/useAuthState";
import { MovementAdminActions } from "../../features/inventory/MovementAdminActions";
import {
  hasAnyCapability,
  hasCapability,
} from "../../shared/api/auth";
import {
  getCatalogCategories,
} from "../../shared/api/catalog";
import {
  getLocations,
  getMovement,
  inventoryRequest,
  movementLabels,
  type Movement,
  type MovementCursorPage,
} from "../../shared/api/inventory";
import "../../features/inventory/inventory.css";
import { PageHeader } from "../../shared/ui";

const PAGE_SIZE = 30;
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function MovementsPage() {
  const auth = useAuthState();
  const user = auth.data?.user;
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedMovementId = searchParams.get("movement");
  const hasValidMovementLink =
    requestedMovementId !== null && UUID_PATTERN.test(requestedMovementId);
  const hasInvalidMovementLink =
    requestedMovementId !== null && !hasValidMovementLink;
  const focusedMovementRef = useRef<HTMLElement>(null);

  const canReadAll = hasCapability(
    user,
    "movement.read_all",
  );

  const canReadMovements = hasAnyCapability(
    user,
    [
      "movement.read_own",
      "movement.read_all",
    ],
  );

  const [period, setPeriod] = useState("3m");
  const [actor, setActor] = useState("");
  const [equipment, setEquipment] = useState("");
  const [location, setLocation] = useState("");
  const [movementType, setMovementType] = useState("");
  const [cursorStack, setCursorStack] = useState<
    Array<string | null>
  >([null]);

  const cursor = cursorStack[cursorStack.length - 1];

  const hierarchy = useQuery({
    staleTime: 5 * 60_000,
    queryKey: ["catalog", "categories"],
    queryFn: ({ signal }) =>
      getCatalogCategories(signal),
    enabled: canReadMovements,
  });

  const locations = useQuery({
    queryKey: ["inventory", "locations"],
    queryFn: ({ signal }) =>
      getLocations(signal),
    enabled: canReadMovements,
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
    enabled: canReadAll,
  });

  const params = new URLSearchParams({
    period,
    limit: String(PAGE_SIZE),
  });

  if (cursor !== null) {
    params.set("cursor", cursor);
  }

  if (canReadAll && actor) {
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
    enabled: canReadMovements && !hasValidMovementLink,
  });

  const focusedMovement = useQuery({
    queryKey: ["inventory", "movement", requestedMovementId],
    queryFn: ({ signal }) => getMovement(requestedMovementId ?? "", signal),
    enabled: canReadMovements && hasValidMovementLink,
  });

  useEffect(() => {
    if (focusedMovement.data) {
      focusedMovementRef.current?.focus();
    }
  }, [focusedMovement.data]);

  const changeFilter = (
    setter: (value: string) => void,
    value: string,
  ) => {
    setter(value);
    setCursorStack([null]);
  };

  const goBack = () => {
    setCursorStack((current) =>
      current.length > 1
        ? current.slice(0, -1)
        : current,
    );
  };

  const goNext = () => {
    const next = history.data?.next_cursor;
    const currentPage = history.data?.cursor;

    if (!next || !currentPage) {
      return;
    }

    setCursorStack((current) => [
      ...current.slice(0, -1),
      currentPage,
      next,
    ]);
  };

  if (auth.isPending) {
    return null;
  }

  if (!canReadMovements) {
    return <Navigate replace to="/catalog" />;
  }

  const displayedMovements = hasValidMovementLink
    ? focusedMovement.data
      ? [focusedMovement.data]
      : []
    : history.data?.items ?? [];

  return (
    <main className="catalog-page">
      <PageHeader
        kicker="Складской журнал"
        title="Движения"
      />

      <div className="catalog-page__body">
        {hasInvalidMovementLink ? (
          <p role="alert">
            Некорректная ссылка на движение. Показан общий журнал.
          </p>
        ) : null}

        {hasValidMovementLink ? (
          <button
            className="button button--ghost"
            onClick={() => setSearchParams({}, { replace: true })}
            type="button"
          >
            Показать весь журнал
          </button>
        ) : null}

        {hasValidMovementLink && focusedMovement.isPending ? (
          <p role="status">Загружаем движение…</p>
        ) : null}

        {hasValidMovementLink && focusedMovement.isError ? (
          <p role="alert">Движение не найдено или недоступно.</p>
        ) : null}

        <div className="history-filters form-surface">
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

          {canReadAll ? (
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
          ) : null}

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

        {!hasValidMovementLink && history.isPending ? (
          <p role="status">
            Загружаем журнал…
          </p>
        ) : null}

        {!hasValidMovementLink && history.isError ? (
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

        {!hasValidMovementLink && history.data?.items.length === 0 ? (
          <p>
            За выбранный период движений нет.
          </p>
        ) : null}

        {displayedMovements.map(
          (movement) => (
            <article
              className="movement-entry"
              key={movement.id}
              ref={movement.id === requestedMovementId ? focusedMovementRef : undefined}
              tabIndex={movement.id === requestedMovementId ? -1 : undefined}
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

              <MovementAdminActions
                movement={movement}
              />

              {movement.procurement_request_id ? (
                <Link to={`/procurement/${movement.procurement_request_id}`}>
                  Открыть закупку
                </Link>
              ) : null}
            </article>
          ),
        )}

        {!hasValidMovementLink ? <div className="warehouse-actions">
          {cursorStack.length > 1 ? (
            <button
              className="button"
              onClick={goBack}
            >
              Назад
            </button>
          ) : null}

          {history.data?.next_cursor ? (
            <button
              className="button"
              onClick={goNext}
            >
              Следующая страница
            </button>
          ) : null}
        </div> : null}
      </div>
    </main>
  );
}
