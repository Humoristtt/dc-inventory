import { expect, it } from "vitest";

import type { CategoryAttribute } from "../../shared/api/catalog";
import { validateDraftAttributes } from "./itemForm";

function attribute(
  key: string,
  dataType: CategoryAttribute["data_type"],
  metadata: CategoryAttribute["validation_metadata"] = null,
): CategoryAttribute {
  return {
    id: `attribute-${key}`,
    key,
    label: key,
    data_type: dataType,
    unit: null,
    required: true,
    filterable: false,
    searchable: false,
    card_visible: false,
    detail_visible: true,
    table_visible: false,
    excel_visible: true,
    sort_order: 10,
    filter_type: "NONE",
    allowed_values: null,
    validation_metadata: metadata,
    is_system: true,
  };
}

it("сохраняет DECIMAL строкой без binary-float coercion", () => {
  const result = validateDraftAttributes(
    [attribute("wavelength", "DECIMAL", { min: 0 })],
    { wavelength: "1271.1234567890" },
  );

  expect(result.errors).toEqual({});
  expect(result.values).toEqual({ wavelength: "1271.1234567890" });
  expect(typeof result.values.wavelength).toBe("string");
});

it("сравнивает decimal bounds точно", () => {
  const result = validateDraftAttributes(
    [attribute("length", "DECIMAL", { min: "0.10000000000000000001" })],
    { length: "0.1" },
  );

  expect(result.errors.length).toContain("Минимальное значение");
});

it("не схлопывает source profile перед отправкой", () => {
  const result = validateDraftAttributes(
    [attribute("reach_profile", "TEXT", { preserve_whitespace: true })],
    { reach_profile: "OM3: до 70 м\nOM4: до 100 м" },
  );

  expect(result.errors).toEqual({});
  expect(result.values.reach_profile).toBe("OM3: до 70 м\nOM4: до 100 м");
});
