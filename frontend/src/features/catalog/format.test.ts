import {
  describe,
  expect,
  it,
} from "vitest";

import {
  formatCatalogAttributeValue,
} from "./format";

describe(
  "catalog attribute formatting",
  () => {
    it(
      "убирает технические trailing zero у DECIMAL",
      () => {
        expect(
          formatCatalogAttributeValue(
            "length",
            "10.0000",
            "м",
            "DECIMAL",
          ),
        ).toBe("10 м");

        expect(
          formatCatalogAttributeValue(
            "length",
            "1.5000000000",
            "м",
            "DECIMAL",
          ),
        ).toBe("1,5 м");
      },
    );

    it(
      "не превращает обычный TEXT в число",
      () => {
        expect(
          formatCatalogAttributeValue(
            "model",
            "10.0000",
            null,
            "TEXT",
          ),
        ).toBe("10.0000");
      },
    );
  },
);
