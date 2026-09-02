import {
  act,
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

import { DebouncedSearchField } from "./DebouncedSearchField";

afterEach(() => {
  vi.useRealTimers();
});

it("debounce объединяет ввод и обрезает бессмысленные пробелы", () => {
  vi.useFakeTimers();
  const onCommit = vi.fn();
  render(
    <DebouncedSearchField
      committedValue=""
      delay={300}
      label="Поиск"
      onCommit={onCommit}
      placeholder="Найти"
    />,
  );

  const input = screen.getByRole("searchbox", { name: "Поиск" });
  fireEvent.change(input, { target: { value: "  Q" } });
  fireEvent.change(input, { target: { value: "  QSFP+  " } });

  act(() => vi.advanceTimersByTime(299));
  expect(onCommit).not.toHaveBeenCalled();

  act(() => vi.advanceTimersByTime(1));
  expect(onCommit).toHaveBeenCalledOnce();
  expect(onCommit).toHaveBeenCalledWith("QSFP+");
  expect(input).toHaveValue("QSFP+");
});
