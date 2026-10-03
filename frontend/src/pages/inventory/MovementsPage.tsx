import { Button } from "../../shared/ui";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";

import { useAuthState } from "../../features/auth/useAuthState";
import { MovementFeed } from "../../features/inventory/MovementFeed";
import { MovementFilters } from "../../features/inventory/MovementFilters";
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
          <Button
            className="button button--ghost"
            onClick={() => setSearchParams({}, { replace: true })}
            type="button"
          >
            Показать весь журнал
          </Button>
        ) : null}

        {hasValidMovementLink && focusedMovement.isPending ? (
          <p role="status">Загружаем движение…</p>
        ) : null}

        {hasValidMovementLink && focusedMovement.isError ? (
          <p role="alert">Движение не найдено или недоступно.</p>
        ) : null}

        <MovementFilters
          actor={actor}
          actors={actors.data ?? []}
          canReadAll={canReadAll}
          categories={
            hierarchy.data ?? []
          }
          equipment={equipment}
          hasError={
            actors.isError
            || hierarchy.isError
            || locations.isError
          }
          location={location}
          locations={
            locations.data ?? []
          }
          movementType={movementType}
          onActorChange={(value) =>
            changeFilter(
              setActor,
              value,
            )
          }
          onEquipmentChange={(value) =>
            changeFilter(
              setEquipment,
              value,
            )
          }
          onLocationChange={(value) =>
            changeFilter(
              setLocation,
              value,
            )
          }
          onMovementTypeChange={(value) =>
            changeFilter(
              setMovementType,
              value,
            )
          }
          onPeriodChange={(value) =>
            changeFilter(
              setPeriod,
              value,
            )
          }
          onRetry={() => {
            void actors.refetch();
            void hierarchy.refetch();
            void locations.refetch();
          }}
          period={period}
        />

        <MovementFeed
          cursorDepth={
            cursorStack.length
          }
          displayedMovements={
            displayedMovements
          }
          focusedMovementError={
            focusedMovement.isError
          }
          focusedMovementPending={
            focusedMovement.isPending
          }
          hasNextPage={
            Boolean(
              history.data
                ?.next_cursor,
            )
          }
          hasValidMovementLink={
            hasValidMovementLink
          }
          historyEmpty={
            history.data
              ?.items.length === 0
          }
          historyError={
            history.isError
          }
          historyPending={
            history.isPending
          }
          movementRef={
            focusedMovementRef
          }
          onBackPage={goBack}
          onNextPage={goNext}
          onRetryHistory={() =>
            void history.refetch()
          }
          requestedMovementId={
            requestedMovementId
          }
        />
      </div>
    </main>
  );
}
