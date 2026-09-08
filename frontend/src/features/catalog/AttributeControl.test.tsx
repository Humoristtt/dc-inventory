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

import type { CategoryAttribute } from "../../shared/api/catalog";
import { AttributeControl } from "./AttributeControl";

afterEach(() => {
  cleanup();
});

const textAttribute: CategoryAttribute = {
  id: "attr-speed",
  key: "speed",
  label: "Скорость",
  data_type: "TEXT",
  unit: null,
  required: true,
  filterable: true,
  searchable: true,
  card_visible: true,
  detail_visible: true,
  table_visible: true,
  excel_visible: true,
  sort_order: 10,
  filter_type: "EXACT",
  allowed_values: null,
  validation_metadata: {
    max_length: 2000,
  },
  is_system: true,
};

it("обычный TEXT остаётся однострочным даже при большом max_length", () => {
  render(
    <AttributeControl
      attribute={textAttribute}
      error={undefined}
      onChange={vi.fn()}
      value=""
    />,
  );

  const control = screen.getByRole(
    "combobox",
    { name: "Скорость" },
  );

  expect(control.tagName).toBe("INPUT");
});

it("показывает существующие значения как умные подсказки", () => {
  const onChange = vi.fn();

  render(
    <AttributeControl
      attribute={textAttribute}
      error={undefined}
      onChange={onChange}
      suggestions={[
        "25 Гбит/с",
        "100 Гбит/с",
      ]}
      value="25"
    />,
  );

  const control = screen.getByRole(
    "combobox",
    { name: "Скорость" },
  );

  fireEvent.focus(control);

  expect(
    screen.getByRole(
      "option",
      { name: "25 Гбит/с" },
    ),
  ).toBeInTheDocument();

  expect(
    screen.queryByRole(
      "option",
      { name: "100 Гбит/с" },
    ),
  ).not.toBeInTheDocument();

  fireEvent.click(
    screen.getByRole(
      "option",
      { name: "25 Гбит/с" },
    ),
  );

  expect(onChange).toHaveBeenCalledWith(
    "25 Гбит/с",
  );
});
