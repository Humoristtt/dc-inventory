import { useCallback, useMemo } from "react";
import {
  type NavigateOptions,
  useSearchParams,
} from "react-router-dom";

import {
  catalogViewStateToSearchParams,
  defaultCatalogSort,
  readCatalogViewState,
  withCatalogFilters,
  withCatalogSort,
  type CatalogFilterState,
  type CatalogSortState,
  type CatalogViewState,
} from "./catalogQuery";

type CatalogViewStateUpdate = (
  current: CatalogViewState,
) => CatalogViewState;

export function useCatalogUrlState(
  defaultSort: CatalogSortState = defaultCatalogSort,
) {
  const {
    sort: defaultSortKey,
    order: defaultSortOrder,
  } = defaultSort;

  const [
    searchParams,
    setSearchParams,
  ] = useSearchParams();

  const serializedSearch =
    searchParams.toString();

  const viewState = useMemo(
    () =>
      readCatalogViewState(
        new URLSearchParams(
          serializedSearch,
        ),
        {
          sort: defaultSortKey,
          order: defaultSortOrder,
        },
      ),
    [
      defaultSortKey,
      defaultSortOrder,
      serializedSearch,
    ],
  );

  const updateViewState = useCallback(
    (
      update: CatalogViewStateUpdate,
      options?: NavigateOptions,
    ) => {
      setSearchParams(
        (currentParams) => {
          const currentState =
            readCatalogViewState(
              currentParams,
              {
                sort: defaultSortKey,
                order: defaultSortOrder,
              },
            );

          const next =
            catalogViewStateToSearchParams(
              update(currentState),
              {
                sort: defaultSortKey,
                order: defaultSortOrder,
              },
            );

          if (
            currentParams.get(
              "long_range",
            ) === "true"
          ) {
            next.set(
              "long_range",
              "true",
            );
          }

          return next;
        },
        options,
      );
    },
    [
      defaultSortKey,
      defaultSortOrder,
      setSearchParams,
    ],
  );

  const updateSearch = useCallback(
    (q: string) => {
      const nextQuery = q.trim();

      updateViewState(
        (current) => {
          const currentQuery =
            current.q.trim();

          const enteringSearch =
            currentQuery === ""
            && nextQuery !== "";

          const leavingSearch =
            currentQuery !== ""
            && nextQuery === "";

          if (
            enteringSearch
            && current.sort
              === defaultSortKey
            && current.order
              === defaultSortOrder
          ) {
            return {
              ...current,
              q,
              sort: "relevance",
              order: "desc",
            };
          }

          if (
            leavingSearch
            && current.sort
              === "relevance"
          ) {
            return {
              ...current,
              q,
              sort: defaultSortKey,
              order: defaultSortOrder,
            };
          }

          return {
            ...current,
            q,
          };
        },
        { replace: true },
      );
    },
    [
      defaultSortKey,
      defaultSortOrder,
      updateViewState,
    ],
  );

  const updateFilters = useCallback(
    (
      filters: CatalogFilterState,
    ) => {
      updateViewState(
        (current) =>
          withCatalogFilters(
            current,
            filters,
          ),
        { replace: true },
      );
    },
    [updateViewState],
  );

  const updateSort = useCallback(
    (
      selection: CatalogSortState,
    ) => {
      updateViewState(
        (current) =>
          withCatalogSort(
            current,
            selection,
          ),
        { replace: true },
      );
    },
    [updateViewState],
  );

  return {
    updateFilters,
    updateSearch,
    updateSort,
    viewState,
  };
}
