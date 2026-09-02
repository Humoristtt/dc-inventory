import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  TELEGRAM_WEB_APP_SDK_PATH,
  getTelegramWebAppSdkLoadStatus,
  loadTelegramWebAppSdk,
} from "./webApp";

function sdkScript(): HTMLScriptElement | null {
  return document.querySelector<HTMLScriptElement>(
    `script[src="${TELEGRAM_WEB_APP_SDK_PATH}"]`,
  );
}

describe("Telegram Web App SDK delivery", () => {
  beforeEach(() => {
    vi.useFakeTimers();

    sdkScript()?.remove();

    Object.defineProperty(window, "Telegram", {
      configurable: true,
      value: undefined,
      writable: true,
    });
  });

  afterEach(() => {
    sdkScript()?.remove();
    vi.useRealTimers();
  });

  it("uses a same-origin vendored SDK path", () => {
    expect(TELEGRAM_WEB_APP_SDK_PATH).toBe(
      "/vendor/telegram/telegram-web-app.js",
    );

    const resolved = new URL(
      TELEGRAM_WEB_APP_SDK_PATH,
      window.location.origin,
    );

    expect(resolved.origin).toBe(window.location.origin);
  });

  it("records timeout instead of silently treating it as Telegram absence", async () => {
    const promise = loadTelegramWebAppSdk();

    const script = sdkScript();

    expect(script).not.toBeNull();
    expect(script?.getAttribute("src")).toBe(
      TELEGRAM_WEB_APP_SDK_PATH,
    );

    await vi.advanceTimersByTimeAsync(3_000);
    await promise;

    expect(getTelegramWebAppSdkLoadStatus()).toBe(
      "timeout",
    );
    expect(sdkScript()).toBeNull();
  });

  it("records a real SDK load error and permits retry", async () => {
    const firstPromise = loadTelegramWebAppSdk();
    const firstScript = sdkScript();

    expect(firstScript).not.toBeNull();

    firstScript?.dispatchEvent(new Event("error"));
    await firstPromise;

    expect(getTelegramWebAppSdkLoadStatus()).toBe(
      "load-error",
    );
    expect(sdkScript()).toBeNull();

    const retryPromise = loadTelegramWebAppSdk();
    const retryScript = sdkScript();

    expect(retryScript).not.toBeNull();

    Object.defineProperty(window, "Telegram", {
      configurable: true,
      value: {
        WebApp: {
          initData: "query_id=test",
          ready: vi.fn(),
          expand: vi.fn(),
        },
      },
      writable: true,
    });

    retryScript?.dispatchEvent(new Event("load"));
    await retryPromise;

    expect(getTelegramWebAppSdkLoadStatus()).toBe(
      "ready",
    );
  });
});
