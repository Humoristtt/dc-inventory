import {
  useInfiniteQuery,
  useQuery,
} from "@tanstack/react-query";
import {
  useMemo,
} from "react";

import {
  getCatalogCategories,
  getCatalogCategory,
  getCatalogItems,
  getCatalogManufacturers,
} from "../../shared/api/catalog";
import {
  catalogItemLabel,
  fuzzyScore,
} from "./catalogItemSearch";

export function useLineComposerCatalogData({
  catalogCategory,
  category,
  manufacturerSearch,
  mode,
  search,
}: {
  catalogCategory: string;
  category: string;
  manufacturerSearch: string;
  mode:
    | "EXISTING_ITEM"
    | "PROPOSED_ITEM";
  search: string;
}) {
  const categories = useQuery({
    queryKey: [
      "catalog",
      "categories",
    ],
    queryFn: ({ signal }) =>
      getCatalogCategories(
        signal,
      ),
    staleTime: 5 * 60_000,
  });

  const leaves = useMemo(() => {
    const all =
      categories.data ?? [];
    const parents = new Set(
      all
        .map(
          (entry) =>
            entry.parent_id,
        )
        .filter(Boolean),
    );

    return all.filter(
      (entry) =>
        !parents.has(entry.id),
    );
  }, [categories.data]);

  const selectedProposedCategory =
    leaves.find(
      (entry) =>
        entry.key === category,
    );

  const identityRequired =
    selectedProposedCategory
      ?.requires_manufacturer_model
      === true;

  const categoryGroups =
    useMemo(() => {
      const all =
        categories.data ?? [];
      const families = all
        .filter(
          (entry) =>
            entry.parent_id
            === null,
        )
        .sort(
          (left, right) =>
            left.sort_order
            - right.sort_order
            || left.display_name
              .localeCompare(
                right.display_name,
                "ru",
              ),
        );

      return families.map(
        (family) => ({
          family,
          children: all
            .filter(
              (entry) =>
                entry.parent_id
                === family.id,
            )
            .sort(
              (left, right) =>
                left.sort_order
                - right.sort_order
                || left.display_name
                  .localeCompare(
                    right
                      .display_name,
                    "ru",
                  ),
            ),
        }),
      );
    }, [categories.data]);

  const schema = useQuery({
    queryKey: [
      "catalog",
      "category",
      category,
    ],
    queryFn: ({ signal }) =>
      getCatalogCategory(
        category,
        signal,
      ),
    enabled:
      Boolean(category),
    staleTime: 5 * 60_000,
  });

  const manufacturers =
    useInfiniteQuery({
      queryKey: [
        "catalog",
        "manufacturers",
        "procurement",
        manufacturerSearch,
      ],
      queryFn: ({
        pageParam,
        signal,
      }) =>
        getCatalogManufacturers(
          {
            q:
              manufacturerSearch,
            limit: 50,
            offset: pageParam,
          },
          signal,
        ),
      initialPageParam: 0,
      getNextPageParam:
        (lastPage) => {
          const nextOffset =
            lastPage.offset
            + lastPage.items
              .length;

          return nextOffset
            < lastPage.total
            ? nextOffset
            : undefined;
        },
      enabled:
        mode
          === "PROPOSED_ITEM"
        && identityRequired,
      staleTime: 5 * 60_000,
    });

  const manufacturerOptions =
    manufacturers.data
      ?.pages.flatMap(
        (page) =>
          page.items,
      ) ?? [];

  const browseItems =
    useInfiniteQuery({
      queryKey: [
        "catalog",
        "procurement-browse",
        catalogCategory,
      ],
      queryFn: ({
        pageParam,
        signal,
      }) =>
        getCatalogItems(
          {
            category:
              catalogCategory
              || undefined,
            limit: 100,
            offset: pageParam,
            sort: "name",
            order: "asc",
          },
          signal,
        ),
      initialPageParam: 0,
      getNextPageParam:
        (lastPage) => {
          const nextOffset =
            lastPage.offset
            + lastPage.items
              .length;

          return nextOffset
            < lastPage.total
            ? nextOffset
            : undefined;
        },
      enabled:
        mode
        === "EXISTING_ITEM",
      staleTime: 60_000,
    });

  const searchItems =
    useInfiniteQuery({
      queryKey: [
        "catalog",
        "procurement-search",
        catalogCategory,
        search,
      ],
      queryFn: ({
        pageParam,
        signal,
      }) =>
        getCatalogItems(
          {
            q: search,
            category:
              catalogCategory
              || undefined,
            limit: 20,
            offset: pageParam,
            sort:
              "relevance",
            order: "desc",
          },
          signal,
        ),
      initialPageParam: 0,
      getNextPageParam:
        (lastPage) => {
          const nextOffset =
            lastPage.offset
            + lastPage.items
              .length;

          return nextOffset
            < lastPage.total
            ? nextOffset
            : undefined;
        },
      enabled:
        mode
          === "EXISTING_ITEM"
        && search.trim()
          .length >= 2,
    });

  const browseOptions =
    useMemo(
      () =>
        browseItems.data
          ?.pages.flatMap(
            (page) =>
              page.items,
          ) ?? [],
      [
        browseItems.data
          ?.pages,
      ],
    );

  const serverSearchOptions =
    useMemo(
      () =>
        searchItems.data
          ?.pages.flatMap(
            (page) =>
              page.items,
          ) ?? [],
      [
        searchItems.data
          ?.pages,
      ],
    );

  const itemOptions =
    useMemo(() => {
      const query =
        search.trim();

      if (query.length < 2) {
        return browseOptions;
      }

      const seen = new Set(
        serverSearchOptions
          .map(
            (item) =>
              item.id,
          ),
      );

      const fuzzy =
        browseOptions
          .map((item) => ({
            item,
            score:
              fuzzyScore(
                item,
                query,
              ),
          }))
          .filter(
            ({
              item,
              score,
            }) =>
              !seen.has(
                item.id,
              )
              && score >= 0.42,
          )
          .sort(
            (left, right) =>
              right.score
              - left.score
              || catalogItemLabel(
                left.item,
              ).localeCompare(
                catalogItemLabel(
                  right.item,
                ),
                "ru",
              ),
          )
          .map(
            ({ item }) =>
              item,
          );

      return [
        ...serverSearchOptions,
        ...fuzzy,
      ];
    }, [
      browseOptions,
      search,
      serverSearchOptions,
    ]);

  const activeItemsQuery =
    search.trim().length >= 2
      ? searchItems
      : browseItems;

  return {
    activeItemsQuery,
    browseItems,
    categoryGroups,
    identityRequired,
    itemOptions,
    leaves,
    manufacturerOptions,
    manufacturers,
    schema,
    searchItems,
  };
}
