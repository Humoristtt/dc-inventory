import { useCallback, useMemo } from "react";
import {
  type NavigateOptions,
  useSearchParams,
} from "react-router-dom";

import {
  catalogViewStateToSearchParams,
  readCatalogViewState,
  withCatalogFilters,
  withCatalogSort,
  type CatalogFilterState,
  type CatalogSortState,
  type CatalogViewState,
} from "./catalogQuery";

type CatalogViewStateUpdate = (current: CatalogViewState) => CatalogViewState;

export function useCatalogUrlState() {
  const [searchParams, setSearchParams] = useSearchParams();
  const serializedSearch = searchParams.toString();
  const viewState = useMemo(
    () => readCatalogViewState(new URLSearchParams(serializedSearch)),
    [serializedSearch],
  );

  const updateViewState = useCallback((
    update: CatalogViewStateUpdate,
    options?: NavigateOptions,
  ) => {
    setSearchParams((currentParams) => {
      const currentState = readCatalogViewState(currentParams);
      const next = catalogViewStateToSearchParams(update(currentState));
      if (currentParams.get("long_range") === "true") next.set("long_range", "true");
      return next;
    }, options);
  }, [setSearchParams]);

  const updateSearch = useCallback((q: string) => {
    updateViewState((current) => ({ ...current, q }), { replace: true });
  }, [updateViewState]);

  const updateFilters = useCallback((filters: CatalogFilterState) => {
    updateViewState((current) => withCatalogFilters(current, filters));
  }, [updateViewState]);

  const updateSort = useCallback((selection: CatalogSortState) => {
    updateViewState((current) => withCatalogSort(current, selection));
  }, [updateViewState]);

  return {
    updateFilters,
    updateSearch,
    updateSort,
    viewState,
  };
}
