import {
  describe,
  expect,
  it,
} from "vitest";

import {
  catalogViewStateToSearchParams,
  readCatalogViewState,
} from "./catalogQuery";
import {
  catalogDefaultSort,
} from "./catalogSort";
import {
  formatCatalogAttributeValue,
} from "./format";

describe("category-aware catalog defaults", () => {
  it("uses available desc for transceivers without polluting URL", () => {
    const defaultSort =
      catalogDefaultSort("sfp");

    expect(defaultSort).toEqual({
      sort: "available",
      order: "desc",
    });

    const state =
      readCatalogViewState(
        new URLSearchParams(),
        defaultSort,
      );

    expect(state.sort)
      .toBe("available");

    expect(state.order)
      .toBe("desc");

    expect(
      catalogViewStateToSearchParams(
        state,
        defaultSort,
      ).toString(),
    ).toBe("");
  });

  it("preserves explicit name asc for transceivers", () => {
    const defaultSort =
      catalogDefaultSort(
        "transceiver_ethernet",
      );

    const params =
      catalogViewStateToSearchParams(
        {
          ...readCatalogViewState(
            new URLSearchParams(),
            defaultSort,
          ),
          sort: "name",
          order: "asc",
        },
        defaultSort,
      );

    expect(params.get("sort"))
      .toBe("name");

    expect(params.get("order"))
      .toBeNull();

    const restored =
      readCatalogViewState(
        params,
        defaultSort,
      );

    expect(restored.sort)
      .toBe("name");

    expect(restored.order)
      .toBe("asc");
  });

  it("preserves available asc against the transceiver default", () => {
    const defaultSort =
      catalogDefaultSort(
        "transceiver_fc",
      );

    const params =
      catalogViewStateToSearchParams(
        {
          ...readCatalogViewState(
            new URLSearchParams(),
            defaultSort,
          ),
          sort: "available",
          order: "asc",
        },
        defaultSort,
      );

    expect(params.get("sort"))
      .toBeNull();

    expect(params.get("order"))
      .toBe("asc");

    const restored =
      readCatalogViewState(
        params,
        defaultSort,
      );

    expect(restored.sort)
      .toBe("available");

    expect(restored.order)
      .toBe("asc");
  });

  it("keeps ordinary categories name asc by default", () => {
    const defaultSort =
      catalogDefaultSort("ssd");

    expect(defaultSort).toEqual({
      sort: "name",
      order: "asc",
    });

    const state =
      readCatalogViewState(
        new URLSearchParams(),
        defaultSort,
      );

    expect(state.sort)
      .toBe("name");

    expect(state.order)
      .toBe("asc");
  });
});

describe("catalog attribute presentation", () => {
  it("uses middle dots for compound reach text", () => {
    expect(
      formatCatalogAttributeValue(
        "reach",
        "OM1: до 33 м / OM2: до 82 м; OM3: до 300 м",
      ),
    ).toBe(
      "OM1: до 33 м · OM2: до 82 м · OM3: до 300 м",
    );
  });

  it("does not rewrite separators in unrelated text attributes", () => {
    expect(
      formatCatalogAttributeValue(
        "application",
        "Ethernet / Storage; Backup",
      ),
    ).toBe(
      "Ethernet / Storage; Backup",
    );
  });
});

describe("catalog speed sort URL state", () => {
  it("сохраняет explicit speed desc", () => {
    const defaultSort =
      catalogDefaultSort(
        "transceiver_ethernet",
      );

    const state =
      readCatalogViewState(
        new URLSearchParams(
          "sort=speed&order=desc",
        ),
        defaultSort,
      );

    expect(state.sort).toBe("speed");
    expect(state.order).toBe("desc");

    const params =
      catalogViewStateToSearchParams(
        state,
        defaultSort,
      );

    expect(params.get("sort"))
      .toBe("speed");

    expect(params.get("order"))
      .toBe("desc");
  });
});
