import {
  act,
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
import { useState } from "react";

import { DebouncedSearchField } from "./DebouncedSearchField";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function CommittedSearchHarness() {
  const [committedValue, setCommittedValue] = useState("");
  return (
    <DebouncedSearchField
      committedValue={committedValue}
      delay={300}
      label="Поиск"
      onCommit={setCommittedValue}
      placeholder="Найти"
    />
  );
}

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

it("commit сохраняет тот же input и фокус без remount", () => {
  vi.useFakeTimers();
  render(<CommittedSearchHarness />);

  const input = screen.getByRole("searchbox", { name: "Поиск" });
  input.focus();
  fireEvent.change(input, { target: { value: "Mellanox" } });

  act(() => vi.advanceTimersByTime(300));

  expect(screen.getByRole("searchbox", { name: "Поиск" })).toBe(input);
  expect(input).toHaveFocus();
  expect(input).toHaveValue("Mellanox");
});

it("external committed value синхронизирует input и отменяет старый debounce", () => {
  vi.useFakeTimers();
  const onCommit = vi.fn();
  const { rerender } = render(
    <DebouncedSearchField
      committedValue="before"
      delay={300}
      label="Поиск"
      onCommit={onCommit}
      placeholder="Найти"
    />,
  );

  const input = screen.getByRole("searchbox", { name: "Поиск" });
  fireEvent.change(input, { target: { value: "pending" } });
  rerender(
    <DebouncedSearchField
      committedValue="from-history"
      delay={300}
      label="Поиск"
      onCommit={onCommit}
      placeholder="Найти"
    />,
  );

  expect(input).toHaveValue("from-history");
  act(() => vi.advanceTimersByTime(300));
  expect(onCommit).not.toHaveBeenCalled();
});
