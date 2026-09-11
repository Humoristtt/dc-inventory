import {
  cleanup,
  render,
  screen,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import {
  afterEach,
  expect,
  it,
} from "vitest";

import type {
  CatalogItemListEntry,
  CategoryAttribute,
} from "../../shared/api/catalog";
import { EquipmentCard } from "./EquipmentCard";

const longModel = "OS2-LC-LC-ULTRA-LONG-MODEL-NAME-THAT-MUST-WRAP-SAFELY";

const item: CatalogItemListEntry = {
  id: "item-1",
  category: { id: "category-1", key: "optics", display_name: "Оптические кабели" },
  manufacturer: null,
  name: "Оптический патч-корд",
  model: longModel,
  status: "ACTIVE",
  archived_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  attributes: {
    length: 3.5,
    duplex: true,
    hidden: "secret",
  },
  inventory: {
    available_count: 4,
    total_count: 4,
  },
};

afterEach(() => {
  cleanup();
});

const attributes: CategoryAttribute[] = [
  {
    id: "attribute-1",
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
  {
    id: "attribute-2",
    key: "duplex",
    label: "Дуплекс",
    data_type: "BOOLEAN",
    unit: null,
    required: false,
    filterable: true,
    searchable: false,
    card_visible: true,
    detail_visible: true,
    table_visible: true,
    excel_visible: true,
    sort_order: 10,
    filter_type: "EXACT",
    allowed_values: null,
    validation_metadata: null,
    is_system: true,
  },
  {
    id: "attribute-3",
    key: "hidden",
    label: "Скрытый атрибут",
    data_type: "TEXT",
    unit: null,
    required: false,
    filterable: false,
    searchable: false,
    card_visible: false,
    detail_visible: true,
    table_visible: false,
    excel_visible: false,
    sort_order: 1,
    filter_type: "NONE",
    allowed_values: null,
    validation_metadata: null,
    is_system: true,
  },
];

it("устойчиво показывает nullable производителя, длинную модель и складской остаток", () => {
  render(
    <MemoryRouter>
      <EquipmentCard attributes={attributes} item={item} returnTo="/catalog/optics?q=lc" />
    </MemoryRouter>,
  );

  expect(screen.getByText("Без производителя")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: longModel })).toBeInTheDocument();
  expect(screen.getByText("3,5 м")).toBeInTheDocument();
  expect(screen.getByText("Да")).toBeInTheDocument();
  expect(screen.queryByText("secret")).not.toBeInTheDocument();

  const available = screen.getByText("В наличии").closest("div");
  expect(available).toHaveTextContent("4");
});

it("явно показывает отсутствие складского остатка", () => {
  render(
    <MemoryRouter>
      <EquipmentCard
        attributes={attributes}
        item={{
          ...item,
          inventory: {
            available_count: 0,
            total_count: 0,
          },
        }}
        returnTo="/catalog/optics"
      />
    </MemoryRouter>,
  );

  const unavailable =
    screen.getByText("Нет в наличии").closest("div");

  expect(unavailable).not.toBeNull();
  expect(unavailable).toHaveTextContent("0");
  expect(
    screen.queryByText("В наличии"),
  ).not.toBeInTheDocument();
});

it("сложную дальность в карточке разделяет средней точкой", () => {
  const reachItem: CatalogItemListEntry = {
    ...item,
    attributes: {
      ...item.attributes,
      reach:
        "OM1: до 33 м / OM2: до 82 м; OM3: до 300 м",
    },
  };

  const reachAttribute: CategoryAttribute = {
    ...attributes[0],
    id: "attribute-reach",
    key: "reach",
    label: "Дальность",
    unit: null,
    sort_order: 1,
  };

  render(
    <MemoryRouter>
      <EquipmentCard
        attributes={[
          reachAttribute,
          ...attributes,
        ]}
        item={reachItem}
        returnTo="/catalog/sfp"
      />
    </MemoryRouter>,
  );

  expect(
    screen.getByText(
      "OM1: до 33 м · OM2: до 82 м · OM3: до 300 м",
    ),
  ).toBeInTheDocument();
});
