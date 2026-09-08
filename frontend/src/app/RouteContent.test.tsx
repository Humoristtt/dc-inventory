import { act, cleanup, render, screen } from "@testing-library/react";
import { lazy } from "react";
import { afterEach, expect, it, vi } from "vitest";

import { RouteContent } from "./RouteContent";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("provides an accessible fallback until the page chunk is ready", async () => {
  let resolve!: (module: { default: () => React.ReactNode }) => void;
  const pending = new Promise<{ default: () => React.ReactNode }>((done) => { resolve = done; });
  const Page = lazy(() => pending);
  render(<RouteContent><Page /></RouteContent>);
  expect(screen.getByRole("status")).toHaveTextContent("Загружаем страницу");
  await act(async () => { resolve({ default: () => <p>Loaded page</p> }); });
  expect(screen.getByText("Loaded page")).toBeInTheDocument();
});

it("provides a recovery action when a page chunk fails", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const Page = lazy(() => Promise.reject(new Error("synthetic chunk failure")));
  await act(async () => { render(<RouteContent><Page /></RouteContent>); });
  expect(screen.getByRole("alert")).toHaveTextContent("Не удалось открыть страницу");
  expect(screen.getByRole("button", { name: "Обновить приложение" })).toBeInTheDocument();
});
