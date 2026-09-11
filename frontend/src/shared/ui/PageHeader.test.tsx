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

it("keeps title in canonical title slot without optional actions", () => {
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
});

it("renders back action through the shared slot", () => {
  const onBack = vi.fn();

  render(
    <PageHeader
      kicker="Каталог"
      onBack={onBack}
      title="Карточка оборудования"
    />,
  );

  fireEvent.click(
    screen.getByRole(
      "button",
      { name: "Назад" },
    ),
  );

  expect(onBack).toHaveBeenCalledTimes(1);
});

it("renders actions and contextual content without changing header anatomy", () => {
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

  expect(
    screen.getByRole(
      "heading",
      { level: 1, name: "Ethernet" },
    ),
  ).toBeInTheDocument();
});
