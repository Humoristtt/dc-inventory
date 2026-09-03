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

const compactTextAttribute: CategoryAttribute = {
  ...integerAttribute,
  id: "compact-text",
  key: "compact_text",
  label: "Compact text",
  data_type: "TEXT",
  filter_type: "NONE",
  validation_metadata: {
    max_length: 5,
  },
};

const preservedTextAttribute: CategoryAttribute = {
  ...integerAttribute,
  id: "preserved-text",
  key: "preserved_text",
  label: "Preserved text",
  data_type: "TEXT",
  filter_type: "NONE",
  validation_metadata: {
    max_length: 4,
    preserve_whitespace: true,
  },
};

it("applies TEXT max_length after compact whitespace normalization", () => {
  const result = validateDraftAttributes(
    [compactTextAttribute],
    { compact_text: "  A   B  " },
  );

  expect(result.errors).toEqual({});
  expect(result.values.compact_text).toBe("A B");
});

it("trims only outer whitespace when preserve_whitespace is enabled", () => {
  const result = validateDraftAttributes(
    [preservedTextAttribute],
    { preserved_text: "  A\n B  " },
  );

  expect(result.errors).toEqual({});
  expect(result.values.preserved_text).toBe("A\n B");
});

it("rejects TEXT when normalized value still exceeds max_length", () => {
  const result = validateDraftAttributes(
    [compactTextAttribute],
    { compact_text: "  ABC   DE  " },
  );

  expect(result.values).toEqual({});
  expect(result.errors.compact_text).toBe("Не более 5 символов");
});
