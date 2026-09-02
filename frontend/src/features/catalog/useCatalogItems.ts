import { useInfiniteQuery } from "@tanstack/react-query";

import {
  catalogQueryCacheKey,
  getCatalogItems,
  type CatalogItemListEntry,
  type CatalogQuery,
} from "../../shared/api/catalog";

const pageSize = 20;

export function useCatalogItems(query: CatalogQuery, enabled = true) {
  const result = useInfiniteQuery({
    queryKey: ["catalog", "items", catalogQueryCacheKey(query)],
    queryFn: ({ pageParam, signal }) =>
      getCatalogItems(
        {
          ...query,
          limit: pageSize,
          offset: pageParam,
        },
        signal,
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const nextOffset = lastPage.offset + lastPage.items.length;
      return nextOffset < lastPage.total ? nextOffset : undefined;
    },
    enabled,
    placeholderData: (previousData) => previousData,
  });

  const itemsById = new Map<string, CatalogItemListEntry>();
  for (const page of result.data?.pages ?? []) {
    for (const item of page.items) {
      if (!itemsById.has(item.id)) {
        itemsById.set(item.id, item);
      }
    }
  }

  return {
    ...result,
    items: [...itemsById.values()],
    total: result.data?.pages.at(-1)?.total ?? 0,
  };
}
