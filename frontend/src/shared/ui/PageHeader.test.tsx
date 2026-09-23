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

import {
  PageHeader,
} from "./PageHeader";

afterEach(() => {
  cleanup();
});

it("keeps an unindented title when back and actions are absent", () => {
  render(
    <PageHeader
      kicker="Каталог"
      title="Редактировать оборудование"
    />,
  );

  const header = screen
    .getByRole("heading", {
      level: 1,
      name: "Редактировать оборудование",
    })
    .closest("[data-ui='page-header']");

  expect(header).not.toBeNull();

  expect(
    header?.querySelector(
      ".ds-page-header__back-slot",
    ),
  ).not.toBeNull();

  expect(
    header?.querySelector(
      ".ds-page-header__actions",
    ),
  ).not.toBeNull();

  const heading = header?.querySelector(".ds-page-header__heading-row");
  expect(heading?.classList.contains("ds-page-header__heading-row--no-back"))
    .toBe(true);
  expect(heading?.classList.contains("ds-page-header__heading-row--no-actions"))
    .toBe(true);
});

it("retains the back-action column and the back button", () => {
  const onBack = vi.fn();

  render(
    <PageHeader
      kicker="Каталог"
      onBack={onBack}
      title="Карточка оборудования"
    />,
  );

  const heading = screen.getByRole("heading", { name: "Карточка оборудования" })
    .closest(".ds-page-header__heading-row");
  expect(heading?.classList.contains("ds-page-header__heading-row--no-back"))
    .toBe(false);

  fireEvent.click(
    screen.getByRole(
      "button",
      { name: "Назад" },
    ),
  );

  expect(onBack).toHaveBeenCalledTimes(1);
});

it("retains contextual actions without adding an empty back column", () => {
  render(
    <PageHeader
      actions={<span>Активно</span>}
      kicker="Категория"
      title="Ethernet"
    >
      <div>Поиск</div>
    </PageHeader>,
  );

  expect(
    screen.getByText("Активно"),
  ).toBeInTheDocument();

  expect(
    screen.getByText("Поиск"),
  ).toBeInTheDocument();

  const heading = screen.getByRole("heading", { level: 1, name: "Ethernet" })
    .closest(".ds-page-header__heading-row");
  expect(heading?.classList.contains("ds-page-header__heading-row--no-back"))
    .toBe(true);
  expect(heading?.classList.contains("ds-page-header__heading-row--no-actions"))
    .toBe(false);
});
