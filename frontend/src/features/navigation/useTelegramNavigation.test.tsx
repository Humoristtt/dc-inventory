import {
  act,
  cleanup,
  render,
  screen,
} from "@testing-library/react";
import {
  MemoryRouter,
  useLocation,
} from "react-router-dom";
import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import { useTelegramNavigation } from "./useTelegramNavigation";

function NavigationHarness() {
  useTelegramNavigation();
  const location = useLocation();
  return <span>{location.pathname}</span>;
}

function telegramBackButton() {
  const handlers: Array<() => void> = [];
  const backButton = {
    show: vi.fn(),
    hide: vi.fn(),
    onClick: vi.fn((handler: () => void) => handlers.push(handler)),
    offClick: vi.fn(),
  };
  window.Telegram = {
    WebApp: {
      initData: "query_id=test",
      ready: vi.fn(),
      expand: vi.fn(),
      BackButton: backButton,
    },
  };
  return { backButton, handlers };
}

afterEach(() => {
  cleanup();
  delete window.Telegram;
});

it("скрывает Telegram BackButton на корне каталога", () => {
  const { backButton } = telegramBackButton();
  render(
    <MemoryRouter initialEntries={["/catalog"]}>
      <NavigationHarness />
    </MemoryRouter>,
  );

  expect(backButton.hide).toHaveBeenCalled();
  expect(backButton.show).not.toHaveBeenCalled();
});

it("показывает BackButton внутри приложения и очищает handler", () => {
  const { backButton, handlers } = telegramBackButton();
  const result = render(
    <MemoryRouter initialEntries={["/catalog/sfp"]}>
      <NavigationHarness />
    </MemoryRouter>,
  );

  expect(backButton.show).toHaveBeenCalledTimes(1);
  expect(backButton.onClick).toHaveBeenCalledTimes(1);
  expect(handlers).toHaveLength(1);

  act(() => handlers[0]?.());

  expect(screen.getByText("/catalog")).toBeInTheDocument();
  expect(backButton.offClick).toHaveBeenCalled();
  expect(backButton.hide).toHaveBeenCalled();

  result.unmount();
  expect(backButton.offClick).toHaveBeenCalledTimes(1);
});
