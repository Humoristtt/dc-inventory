import {
  cleanup,
  render,
  screen,
} from "@testing-library/react";
import {
  afterEach,
  expect,
  it,
} from "vitest";

import {
  Button,
  Input,
  Select,
  Textarea,
} from "./controls";

afterEach(() => {
  cleanup();
});

it("disables browser text assistance for input controls", () => {
  render(
    <Input
      aria-label="Наименование"
      autoCapitalize="sentences"
      autoComplete="name"
      autoCorrect="on"
      spellCheck
    />,
  );

  const input = screen.getByRole(
    "textbox",
    { name: "Наименование" },
  );

  expect(input).toHaveAttribute(
    "autocomplete",
    "off",
  );
  expect(input).toHaveAttribute(
    "autocorrect",
    "off",
  );
  expect(input).toHaveAttribute(
    "autocapitalize",
    "none",
  );
  expect(input).toHaveAttribute(
    "spellcheck",
    "false",
  );
  expect(input).toHaveClass(
    "ds-control",
    "ds-input",
  );
});

it("disables browser text assistance for textareas", () => {
  render(
    <Textarea
      aria-label="Комментарий"
      autoCapitalize="sentences"
      autoComplete="on"
      autoCorrect="on"
      spellCheck
    />,
  );

  const textarea = screen.getByRole(
    "textbox",
    { name: "Комментарий" },
  );

  expect(textarea).toHaveAttribute(
    "autocomplete",
    "off",
  );
  expect(textarea).toHaveAttribute(
    "autocorrect",
    "off",
  );
  expect(textarea).toHaveAttribute(
    "autocapitalize",
    "none",
  );
  expect(textarea).toHaveAttribute(
    "spellcheck",
    "false",
  );
  expect(textarea).toHaveClass(
    "ds-control",
    "ds-textarea",
  );
});

it("keeps select and button on shared primitives", () => {
  render(
    <>
      <Select aria-label="Статус">
        <option value="active">Активен</option>
      </Select>
      <Button>Сохранить</Button>
    </>,
  );

  expect(
    screen.getByRole(
      "combobox",
      { name: "Статус" },
    ),
  ).toHaveClass(
    "ds-control",
    "ds-select",
  );

  const button = screen.getByRole(
    "button",
    { name: "Сохранить" },
  );

  expect(button).toHaveAttribute(
    "type",
    "button",
  );
  expect(button).toHaveClass(
    "ds-button",
    "button",
  );
});
