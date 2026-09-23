import { describe, expect, it } from "vitest";

import type {
  CatalogAttributeFilter,
  CatalogFacet,
} from "../../shared/api/catalog";
import {
  applySpeedBucket,
  isSpeedBucketSelected,
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

  it("replaces raw speed filters while preserving unrelated filters", () => {
    const current: CatalogAttributeFilter[] = [
      {
        key: "connector",
        operator: "eq",
        value: "LC",
      },
      {
        key: "speed",
        operator: "eq",
        value: "40 Гбит/с",
      },
    ];
    const values = speedFacetValuesForBucket(
      facet,
      25,
    );
    const next = applySpeedBucket(
      current,
      values,
      { clear: false },
    );

    expect(next).toEqual([
      {
        key: "connector",
        operator: "eq",
        value: "LC",
      },
      {
        key: "speed",
        operator: "eq",
        value: "25 Гбит/с",
      },
      {
        key: "speed",
        operator: "eq",
        value: "10/25 Гбит/с",
      },
    ]);
    expect(
      isSpeedBucketSelected(
        next,
        values,
      ),
    ).toBe(true);
  });
});
