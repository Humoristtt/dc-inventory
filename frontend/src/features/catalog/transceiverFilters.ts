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

export function isSpeedBucketSelected(
  filters: readonly CatalogAttributeFilter[],
  values: readonly string[],
): boolean {
  if (values.length === 0) {
    return false;
  }

  const selected = filters
    .filter(
      (filter) =>
        filter.key === "speed"
        && filter.operator === "eq",
    )
    .map((filter) => filter.value)
    .sort();

  const expected = [...values].sort();

  return (
    selected.length === expected.length
    && selected.every(
      (value, index) => value === expected[index],
    )
  );
}

export function applySpeedBucket(
  filters: readonly CatalogAttributeFilter[],
  values: readonly string[],
  { clear }: { clear: boolean },
): CatalogAttributeFilter[] {
  const remaining = filters.filter(
    (filter) => filter.key !== "speed",
  );

  if (clear) {
    return remaining;
  }

  return [
    ...remaining,
    ...values.map(
      (value): CatalogAttributeFilter => ({
        key: "speed",
        operator: "eq",
        value,
      }),
    ),
  ];
}
