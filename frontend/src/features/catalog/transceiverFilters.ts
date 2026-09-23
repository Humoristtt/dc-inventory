import type {
  CatalogAttributeFilter,
  CatalogFacet,
} from "../../shared/api/catalog";

export const ETHERNET_SPEED_BUCKETS = [
  100,
  40,
  25,
  10,
] as const;

export type EthernetSpeedBucket =
  typeof ETHERNET_SPEED_BUCKETS[number];

function speedNumbers(value: string): number[] {
  if (!/Гбит\/с/i.test(value)) {
    return [];
  }

  return Array.from(
    value.matchAll(/\d+(?:[.,]\d+)?/g),
    (match) => Number(match[0].replace(",", ".")),
  ).filter(Number.isFinite);
}

export function speedFacetValuesForBucket(
  facet: CatalogFacet | undefined,
  bucket: EthernetSpeedBucket,
): string[] {
  if (facet?.key !== "speed") {
    return [];
  }

  return facet.values
    .filter((entry) =>
      speedNumbers(String(entry.value))
        .includes(bucket),
    )
    .map((entry) => String(entry.value));
}

export function speedFacetCountForBucket(
  facet: CatalogFacet | undefined,
  bucket: EthernetSpeedBucket,
): number {
  if (facet?.key !== "speed") {
    return 0;
  }

  return facet.values
    .filter((entry) =>
      speedNumbers(String(entry.value))
        .includes(bucket),
    )
    .reduce(
      (total, entry) => total + entry.count,
      0,
    );
}

function selectedSpeedValues(
  filters: readonly CatalogAttributeFilter[],
): Set<string> {
  return new Set(
    filters
      .filter(
        (filter) =>
          filter.key === "speed"
          && filter.operator === "eq",
      )
      .map((filter) => filter.value),
  );
}

export function isSpeedBucketSelected(
  filters: readonly CatalogAttributeFilter[],
  values: readonly string[],
): boolean {
  if (values.length === 0) {
    return false;
  }

  const selected = selectedSpeedValues(filters);

  return values.every((value) =>
    selected.has(value),
  );
}

export function toggleSpeedBucket(
  filters: readonly CatalogAttributeFilter[],
  facet: CatalogFacet | undefined,
  bucket: EthernetSpeedBucket,
): CatalogAttributeFilter[] {
  const remaining = filters.filter(
    (filter) => filter.key !== "speed",
  );
  const currentValues =
    selectedSpeedValues(filters);

  const selectedBuckets = new Set(
    ETHERNET_SPEED_BUCKETS.filter(
      (candidate) => {
        const values =
          speedFacetValuesForBucket(
            facet,
            candidate,
          );

        return (
          values.length > 0
          && values.every((value) =>
            currentValues.has(value),
          )
        );
      },
    ),
  );

  if (selectedBuckets.has(bucket)) {
    selectedBuckets.delete(bucket);
  } else {
    selectedBuckets.add(bucket);
  }

  const nextValues = new Set<string>();

  for (const selectedBucket of selectedBuckets) {
    for (const value of speedFacetValuesForBucket(
      facet,
      selectedBucket,
    )) {
      nextValues.add(value);
    }
  }

  return [
    ...remaining,
    ...[...nextValues]
      .sort((left, right) =>
        left.localeCompare(right, "ru"),
      )
      .map(
        (value): CatalogAttributeFilter => ({
          key: "speed",
          operator: "eq",
          value,
        }),
      ),
  ];
}
