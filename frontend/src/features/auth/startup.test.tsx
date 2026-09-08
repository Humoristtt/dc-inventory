import { act, cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

let client: QueryClient;
const approved = {
  user: { id: "synthetic", role: "USER", access_status: "APPROVED" },
  support: { username: "support", url: "https://t.me/support" },
};

beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  delete window.Telegram;
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});
afterEach(() => {
  cleanup();
  client.clear();
  document.querySelector('script[src="/vendor/telegram/telegram-web-app.js"]')?.remove();
  delete window.Telegram;
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function availableSdk(initData = "synthetic-init-data") {
  const sdk = { initData, ready: vi.fn(), expand: vi.fn() };
  window.Telegram = { WebApp: sdk };
  return sdk;
}

async function start(cookieSession = false) {
  const fetchMock = vi.fn(async (url: RequestInfo | URL) =>
    String(url) === "/api/auth/me" && !cookieSession
      ? new Response(null, { status: 401 })
      : new Response(JSON.stringify(approved), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const { TelegramAccessGate } = await import("./TelegramAccessGate");
  render(<StrictMode><QueryClientProvider client={client}>
    <TelegramAccessGate><p>Application ready</p></TelegramAccessGate>
  </QueryClientProvider></StrictMode>);
  return fetchMock;
}

async function settle() {
  await act(async () => { await vi.advanceTimersByTimeAsync(10); });
}

it("renders the shell immediately and shares delayed authentication across StrictMode", async () => {
  const fetchMock = await start();
  expect(screen.getByRole("status")).toHaveTextContent("Подтверждаем Telegram-сессию");
  await settle();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const sdk = availableSdk();
  await act(async () => {
    document.querySelector("script")?.dispatchEvent(new Event("load"));
  });
  await settle();
  expect(screen.getByText("Application ready")).toBeInTheDocument();
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/auth/me", "/api/auth/telegram"]);
  expect(sdk.ready).toHaveBeenCalledTimes(1);
  expect(sdk.expand).toHaveBeenCalledTimes(1);
});

it.each(["error", "timeout"])("shows a deterministic SDK %s state without attempting Telegram auth", async (failure) => {
  const fetchMock = await start();
  await settle();
  await act(async () => {
    if (failure === "error") document.querySelector("script")?.dispatchEvent(new Event("error"));
    else await vi.advanceTimersByTimeAsync(3_000);
  });
  await settle();
  expect(screen.getByRole("heading", { name: "Не удалось загрузить Telegram" })).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it("uses an existing SDK without injecting a script or duplicating auth", async () => {
  const sdk = availableSdk();
  const fetchMock = await start();
  await settle();
  expect(screen.getByText("Application ready")).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(sdk.ready).toHaveBeenCalledTimes(1);
});

it("shows the browser fallback after a loaded SDK supplies no initData", async () => {
  availableSdk("");
  const fetchMock = await start();
  await settle();
  expect(screen.getByRole("heading", { name: "Откройте приложение через Telegram" })).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it("allows an existing cookie session to proceed while the SDK is still loading", async () => {
  const fetchMock = await start(true);
  await settle();
  expect(screen.getByText("Application ready")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});
