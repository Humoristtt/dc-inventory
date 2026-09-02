import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";

import type {
  CatalogItemListEntry,
  CategoryAttribute,
} from "../../shared/api/catalog";
import { EquipmentCard } from "./EquipmentCard";

const longModel = "OS2-LC-LC-ULTRA-LONG-MODEL-NAME-THAT-MUST-WRAP-SAFELY";
const longPartNumber = "PN-1234567890-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0987654321";

const item: CatalogItemListEntry = {
  id: "item-1",
  category: { id: "category-1", key: "optics", display_name: "Оптические кабели" },
  manufacturer: null,
  name: "Оптический патч-корд",
  model: longModel,
  manufacturer_part_number: longPartNumber,
  internal_code: null,
  description: null,
  accounting_mode: "QUANTITY",
  status: "ACTIVE",
  comment: null,
  datasheet_url: null,
  technical_data_source: null,
  archived_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  attributes: {
    length: 3.5,
    duplex: true,
    hidden: "secret",
  },
  inventory: {
    available_count: 0,
    custody_count: 4,
    total_count: 4,
  },
};

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

it("устойчиво показывает nullable производителя, длинные идентификаторы и остатки", () => {
  render(
    <MemoryRouter>
      <EquipmentCard attributes={attributes} item={item} returnTo="/catalog/optics?q=lc" />
    </MemoryRouter>,
  );

  expect(screen.getByText("Без производителя")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: longModel })).toBeInTheDocument();
  expect(screen.getByText(`PN ${longPartNumber}`)).toBeInTheDocument();
  expect(screen.getByText("3,5 м")).toBeInTheDocument();
  expect(screen.getByText("Да")).toBeInTheDocument();
  expect(screen.queryByText("secret")).not.toBeInTheDocument();

  const available = screen.getByText("Доступно").closest("div");
  const custody = screen.getByText("У пользователей").closest("div");
  expect(available).toHaveTextContent("0");
  expect(custody).toHaveTextContent("4");
});
