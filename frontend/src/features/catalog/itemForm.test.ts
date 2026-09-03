import {
  expect,
  it,
} from "vitest";

import type {
  CategoryAttribute,
} from "../../shared/api/catalog";
import {
  validateDraftAttributes,
} from "./itemForm";

const integerAttribute: CategoryAttribute = {
  id: "integer-attribute",
  key: "integer",
  label: "Integer",
  data_type: "INTEGER",
  unit: null,
  required: true,
  filterable: true,
  searchable: true,
  card_visible: true,
  detail_visible: true,
  table_visible: true,
  excel_visible: true,
  sort_order: 10,
  filter_type: "RANGE",
  allowed_values: null,
  validation_metadata: null,
  is_system: true,
};

it("accepts exact JavaScript-safe INTEGER boundaries", () => {
  const maximum = validateDraftAttributes(
    [integerAttribute],
    { integer: String(Number.MAX_SAFE_INTEGER) },
  );

  const minimum = validateDraftAttributes(
    [integerAttribute],
    { integer: String(Number.MIN_SAFE_INTEGER) },
  );

  expect(maximum.errors).toEqual({});
  expect(maximum.values.integer).toBe(Number.MAX_SAFE_INTEGER);

  expect(minimum.errors).toEqual({});
  expect(minimum.values.integer).toBe(Number.MIN_SAFE_INTEGER);
});

it("rejects INTEGER values that cannot round-trip exactly through JSON number", () => {
  const above = validateDraftAttributes(
    [integerAttribute],
    { integer: "9007199254740992" },
  );

  const below = validateDraftAttributes(
    [integerAttribute],
    { integer: "-9007199254740992" },
  );

  expect(above.values).toEqual({});
  expect(below.values).toEqual({});

  expect(above.errors.integer).toBe(
    "Число слишком велико для безопасной отправки",
  );

  expect(below.errors.integer).toBe(
    "Число слишком велико для безопасной отправки",
  );
});
