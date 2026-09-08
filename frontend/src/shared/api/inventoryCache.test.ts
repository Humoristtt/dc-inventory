import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";

import { refreshAfterLocationEdit, refreshAfterMovement } from "./inventoryCache";

const keys = [
  ["inventory", "summary", "changed"], ["inventory", "summary", "other"],
  ["inventory", "locations"], ["inventory", "movements", "filter"], ["inventory", "actors"],
  ["catalog", "items", "filter"], ["catalog", "facets", "filter"],
  ["catalog", "item", "changed"], ["catalog", "category", "cable"], ["catalog", "categories"],
];

it.each([
  ["movement", [0, 3, 4, 5, 6]],
  ["location", [0, 1, 2, 6]],
] as const)("refreshes exactly the affected %s queries and waits for authoritative results", async (kind, changed) => {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
  const fetches = keys.map(() => vi.fn(async () => "server result"));
  const unsubscribers = keys.map((queryKey, index) => {
    client.setQueryData(queryKey, "cached");
    return new QueryObserver(client, { queryKey, queryFn: fetches[index] }).subscribe(() => {});
  });
  try {
    if (kind === "movement") await refreshAfterMovement(client, "changed");
    else await refreshAfterLocationEdit(client);
    fetches.forEach((fetch, index) => {
      const affected = (changed as readonly number[]).includes(index);
      expect(fetch).toHaveBeenCalledTimes(affected ? 1 : 0);
      expect(client.getQueryData(keys[index])).toBe(affected ? "server result" : "cached");
    });
  } finally {
    unsubscribers.forEach((unsubscribe) => unsubscribe());
    client.clear();
  }
});
