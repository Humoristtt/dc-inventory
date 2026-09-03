import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import type {
  CatalogFacet,
  CategoryAttribute,
} from "../../shared/api/catalog";
import {
  defaultCatalogFilterState,
  type CatalogFilterState,
} from "./catalogQuery";
import { FilterSheet } from "./FilterSheet";

afterEach(cleanup);

const attributes: CategoryAttribute[] = [
  {
    id: "a-speed",
    key: "speed",
    label: "Скорость",
    data_type: "ENUM",
    unit: null,
    required: false,
    filterable: true,
    searchable: true,
    card_visible: true,
    detail_visible: true,
    table_visible: true,
    excel_visible: true,
    sort_order: 10,
    filter_type: "EXACT",
    allowed_values: ["10G", "25G"],
    validation_metadata: null,
    is_system: true,
  },
  {
    id: "a-length",
    key: "length",
    label: "Длина",
    data_type: "DECIMAL",
    unit: "м",
    required: false,
    filterable: true,
    searchable: true,
    card_visible: true,
    detail_visible: true,
    table_visible: true,
    excel_visible: true,
    sort_order: 20,
    filter_type: "RANGE",
    allowed_values: null,
    validation_metadata: null,
    is_system: true,
  },
];

const facets: CatalogFacet[] = [
  {
    key: "manufacturer",
    label: "Производитель",
    data_type: "TEXT",
    unit: null,
    filter_type: "EXACT",
    values: [
      { value: "m-1", count: 8, label: "Mellanox", code: null, name: null },
    ],
    min: null,
    max: null,
  },
  {
    key: "speed",
    label: "Скорость backend",
    data_type: "ENUM",
    unit: null,
    filter_type: "EXACT",
    values: [
      { value: "10G", count: 5, label: "10G", code: null, name: null },
      { value: "25G", count: 3, label: "25G", code: null, name: null },
    ],
    min: null,
    max: null,
  },
  {
    key: "length",
    label: "Длина backend",
    data_type: "DECIMAL",
    unit: "м",
    filter_type: "RANGE",
    values: [],
    min: 1,
    max: 30,
  },
];

function renderSheet(
  active: CatalogFilterState = defaultCatalogFilterState,
  onApply = vi.fn(),
  onCancel = vi.fn(),
) {
  render(
    <FilterSheet
      active={active}
      attributes={attributes}
      facets={facets}
      onApply={onApply}
      onCancel={onCancel}
    />,
  );
  return { onApply, onCancel };
}

it("Apply фиксирует draft exact и range фильтры", () => {
  const { onApply } = renderSheet();

  fireEvent.click(screen.getByLabelText("Mellanox"));
  fireEvent.click(screen.getByLabelText("10G"));
  fireEvent.click(screen.getByLabelText("25G"));
  fireEvent.change(screen.getByLabelText("Длина: от"), { target: { value: "2.5" } });
  fireEvent.change(screen.getByLabelText("Длина: до"), { target: { value: "10" } });
  fireEvent.click(screen.getByRole("button", { name: "Применить" }));

  expect(onApply).toHaveBeenCalledTimes(1);
  const next = onApply.mock.calls[0]?.[0] as CatalogFilterState;
  expect(next.manufacturerIds).toEqual(["m-1"]);
  expect(next.filters).toEqual(expect.arrayContaining([
    { key: "speed", operator: "eq", value: "10G" },
    { key: "speed", operator: "eq", value: "25G" },
    { key: "length", operator: "gte", value: "2.5" },
    { key: "length", operator: "lte", value: "10" },
  ]));
});

it("Cancel не применяет draft", () => {
  const { onApply, onCancel } = renderSheet();
  fireEvent.click(screen.getByLabelText("Mellanox"));
  fireEvent.click(screen.getByRole("button", { name: "Закрыть фильтры" }));

  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(onApply).not.toHaveBeenCalled();
});

it("Reset очищает выбранные значения перед Apply", () => {
  const active: CatalogFilterState = {
    ...defaultCatalogFilterState,
    manufacturerIds: ["m-1"],
    filters: [{ key: "speed", operator: "eq", value: "10G" }],
  };
  const { onApply } = renderSheet(active);

  fireEvent.click(screen.getByRole("button", { name: "Сбросить" }));
  fireEvent.click(screen.getByRole("button", { name: "Применить" }));

  const next = onApply.mock.calls[0]?.[0] as CatalogFilterState;
  expect(next.manufacturerIds).toEqual([]);
  expect(next.filters).toEqual([]);
});

it("Apply возвращает только filter-owned state", () => {
  const { onApply } = renderSheet();
  fireEvent.click(screen.getByLabelText("Mellanox"));
  fireEvent.click(screen.getByRole("button", { name: "Применить" }));

  expect(onApply).toHaveBeenCalledWith(expect.objectContaining({
    manufacturerIds: ["m-1"],
    status: "ACTIVE",
  }));
  expect(onApply.mock.calls[0]?.[0]).not.toHaveProperty("q");
  expect(onApply.mock.calls[0]?.[0]).not.toHaveProperty("sort");
  expect(onApply.mock.calls[0]?.[0]).not.toHaveProperty("order");
});

it("скрывает facet-группы без доступных значений или range bounds", () => {
  const emptyFacets: CatalogFacet[] = [
    {
      key: "manufacturer",
      label: "Производитель",
      data_type: "TEXT",
      unit: null,
      filter_type: "EXACT",
      values: [],
      min: null,
      max: null,
    },
    {
      key: "length",
      label: "Длина backend",
      data_type: "DECIMAL",
      unit: "м",
      filter_type: "RANGE",
      values: [],
      min: null,
      max: null,
    },
  ];

  render(
    <FilterSheet
      active={defaultCatalogFilterState}
      attributes={attributes}
      facets={emptyFacets}
      onApply={vi.fn()}
      onCancel={vi.fn()}
    />,
  );

  expect(screen.queryByText("Производитель")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Длина: от")).not.toBeInTheDocument();
  expect(
    screen.getByText("Для этой выборки фильтры недоступны."),
  ).toBeInTheDocument();
});

it("не скрывает пустой facet, если в нём уже есть активный фильтр", () => {
  const active: CatalogFilterState = {
    ...defaultCatalogFilterState,
    manufacturerIds: ["m-1"],
    filters: [{ key: "length", operator: "gte", value: "2.5" }],
  };
  const emptyFacets: CatalogFacet[] = [
    {
      key: "manufacturer",
      label: "Производитель",
      data_type: "TEXT",
      unit: null,
      filter_type: "EXACT",
      values: [],
      min: null,
      max: null,
    },
    {
      key: "length",
      label: "Длина backend",
      data_type: "DECIMAL",
      unit: "м",
      filter_type: "RANGE",
      values: [],
      min: null,
      max: null,
    },
  ];

  render(
    <FilterSheet
      active={active}
      attributes={attributes}
      facets={emptyFacets}
      onApply={vi.fn()}
      onCancel={vi.fn()}
    />,
  );

  expect(screen.getByLabelText("m-1")).toBeChecked();
  expect(screen.getByLabelText("Длина: от")).toHaveValue(2.5);
});
