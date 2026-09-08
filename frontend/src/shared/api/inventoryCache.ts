import type { QueryClient } from "@tanstack/react-query";

export async function refreshAfterMovement(client: QueryClient, itemId: string): Promise<void> {
  // Quantities remain server-authoritative. Metadata and other item summaries
  // are unchanged; every filtered list/facet/history may gain or lose a match.
  await Promise.all([
    client.invalidateQueries({ queryKey: ["inventory", "summary", itemId], exact: true }),
    client.invalidateQueries({ queryKey: ["inventory", "movements"] }),
    client.invalidateQueries({ queryKey: ["inventory", "actors"] }),
    client.invalidateQueries({ queryKey: ["catalog", "items"] }),
    client.invalidateQueries({ queryKey: ["catalog", "facets"] }),
  ]);
}

export async function refreshAfterLocationEdit(client: QueryClient): Promise<void> {
  // Current summaries and facets embed location labels. Journal labels are
  // immutable snapshots and must not be refreshed as if they were live names.
  await Promise.all([
    client.invalidateQueries({ queryKey: ["inventory", "locations"] }),
    client.invalidateQueries({ queryKey: ["inventory", "summary"] }),
    client.invalidateQueries({ queryKey: ["catalog", "facets"] }),
  ]);
}
