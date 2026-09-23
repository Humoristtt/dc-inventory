import { describe, expect, it } from "vitest";

import type {
  CatalogAttributeFilter,
  CatalogFacet,
} from "../../shared/api/catalog";
import {
  isSpeedBucketSelected,
  toggleSpeedBucket,
  speedFacetCountForBucket,
  speedFacetValuesForBucket,
} from "./transceiverFilters";

const facet: CatalogFacet = {
  key: "speed",
  label: "Скорость",
  data_type: "TEXT",
  unit: null,
  filter_type: "EXACT",
  values_has_more: false,
  values: [
    { value: "100 Гбит/с", count: 2, label: null, code: null, name: null },
    { value: "40 Гбит/с", count: 3, label: null, code: null, name: null },
    { value: "25 Гбит/с", count: 4, label: null, code: null, name: null },
    { value: "10/25 Гбит/с", count: 5, label: null, code: null, name: null },
    { value: "10 Гбит/с", count: 6, label: null, code: null, name: null },
    { value: "1 Гбит/с", count: 7, label: null, code: null, name: null },
  ],
  min: null,
  max: null,
};

describe("Ethernet transceiver speed buckets", () => {
  it("puts a dual-rate 10/25 module into both 10 and 25 Gbit/s buckets", () => {
    expect(
      speedFacetValuesForBucket(facet, 25),
    ).toEqual([
      "25 Гбит/с",
      "10/25 Гбит/с",
    ]);
    expect(
      speedFacetValuesForBucket(facet, 10),
    ).toEqual([
      "10/25 Гбит/с",
      "10 Гбит/с",
    ]);

    expect(
      speedFacetCountForBucket(facet, 25),
    ).toBe(9);
    expect(
      speedFacetCountForBucket(facet, 10),
    ).toBe(11);
  });

  it("only exposes values belonging to the requested high-speed bucket", () => {
    expect(
      speedFacetValuesForBucket(facet, 100),
    ).toEqual(["100 Гбит/с"]);
    expect(
      speedFacetValuesForBucket(facet, 40),
    ).toEqual(["40 Гбит/с"]);
  });

  it("allows selecting several speed buckets at once", () => {
    const base: CatalogAttributeFilter[] = [
      {
        key: "connector",
        operator: "eq",
        value: "LC",
      },
    ];

    const with25 = toggleSpeedBucket(
      base,
      facet,
      25,
    );
    const with25And10 = toggleSpeedBucket(
      with25,
      facet,
      10,
    );
    const withThree = toggleSpeedBucket(
      with25And10,
      facet,
      40,
    );
    const all = toggleSpeedBucket(
      withThree,
      facet,
      100,
    );

    expect(
      isSpeedBucketSelected(
        all,
        speedFacetValuesForBucket(
          facet,
          100,
        ),
      ),
    ).toBe(true);
    expect(
      isSpeedBucketSelected(
        all,
        speedFacetValuesForBucket(
          facet,
          40,
        ),
      ),
    ).toBe(true);
    expect(
      isSpeedBucketSelected(
        all,
        speedFacetValuesForBucket(
          facet,
          25,
        ),
      ),
    ).toBe(true);
    expect(
      isSpeedBucketSelected(
        all,
        speedFacetValuesForBucket(
          facet,
          10,
        ),
      ),
    ).toBe(true);

    expect(
      all
        .filter(
          (filter) =>
            filter.key === "speed",
        )
        .map((filter) => filter.value),
    ).toEqual([
      "10 Гбит/с",
      "10/25 Гбит/с",
      "100 Гбит/с",
      "25 Гбит/с",
      "40 Гбит/с",
    ]);

    expect(all[0]).toEqual(base[0]);
  });

  it("keeps the shared 10/25 value when one overlapping bucket is disabled", () => {
    let filters: CatalogAttributeFilter[] = [];

    filters = toggleSpeedBucket(
      filters,
      facet,
      25,
    );
    filters = toggleSpeedBucket(
      filters,
      facet,
      10,
    );
    filters = toggleSpeedBucket(
      filters,
      facet,
      10,
    );

    expect(
      filters
        .filter(
          (filter) =>
            filter.key === "speed",
        )
        .map((filter) => filter.value),
    ).toEqual([
      "10/25 Гбит/с",
      "25 Гбит/с",
    ]);

    expect(
      isSpeedBucketSelected(
        filters,
        speedFacetValuesForBucket(
          facet,
          25,
        ),
      ),
    ).toBe(true);
    expect(
      isSpeedBucketSelected(
        filters,
        speedFacetValuesForBucket(
          facet,
          10,
        ),
      ),
    ).toBe(false);
  });
});
