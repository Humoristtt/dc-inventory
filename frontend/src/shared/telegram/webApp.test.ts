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
  loadTelegramWebAppSdk,
} from "./webApp";

describe("Telegram Web App SDK delivery", () => {
  beforeEach(() => {
    vi.useFakeTimers();

    document
      .querySelectorAll(
        `script[src="${TELEGRAM_WEB_APP_SDK_PATH}"]`,
      )
      .forEach((element) => {
        element.remove();
      });

    Object.defineProperty(window, "Telegram", {
      configurable: true,
      value: undefined,
      writable: true,
    });
  });

  afterEach(() => {
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

  it("appends only the same-origin SDK script", async () => {
    const promise = loadTelegramWebAppSdk();

    const script =
      document.querySelector<HTMLScriptElement>(
        `script[src="${TELEGRAM_WEB_APP_SDK_PATH}"]`,
      );

    expect(script).not.toBeNull();
    expect(script?.getAttribute("src")).toBe(
      TELEGRAM_WEB_APP_SDK_PATH,
    );

    const resolved = new URL(
      script?.src ?? "",
      window.location.origin,
    );

    expect(resolved.origin).toBe(window.location.origin);

    await vi.runAllTimersAsync();
    await promise;
  });
});
