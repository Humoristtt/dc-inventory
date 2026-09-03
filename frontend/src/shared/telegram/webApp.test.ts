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
  bindDesktopEscapeGuard,
  bindTelegramBackButton,
  getTelegramWebAppSdkLoadStatus,
  loadTelegramWebAppSdk,
  prepareTelegramWebApp,
  requestTelegramFullscreen,
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

  it("prepares Telegram viewport and applies runtime safe areas", () => {
    const ready = vi.fn();
    const expand = vi.fn();
    window.Telegram = {
      WebApp: {
        initData: "query_id=test",
        ready,
        expand,
        contentSafeAreaInset: {
          top: 12,
          right: 2,
          bottom: 18,
          left: 2,
        },
      },
    };

    prepareTelegramWebApp();

    expect(ready).toHaveBeenCalledTimes(1);
    expect(expand).toHaveBeenCalledTimes(1);
    expect(document.documentElement.style.getPropertyValue("--app-safe-area-bottom")).toBe("18px");
  });

  it("uses expanded windowed mode without requesting fullscreen", () => {
    const ready = vi.fn();
    const expand = vi.fn();
    const requestFullscreen = vi.fn();

    window.Telegram = {
      WebApp: {
        initData: "query_id=test",
        ready,
        expand,
        requestFullscreen,
      },
    };

    prepareTelegramWebApp();

    expect(ready).toHaveBeenCalledTimes(1);
    expect(expand).toHaveBeenCalledTimes(1);
    expect(requestFullscreen).not.toHaveBeenCalled();
  });

  it("requests fullscreen only after explicit user action", () => {
    const requestFullscreen = vi.fn();

    window.Telegram = {
      WebApp: {
        initData: "query_id=test",
        ready: vi.fn(),
        expand: vi.fn(),
        requestFullscreen,
      },
    };

    expect(requestTelegramFullscreen()).toBe(true);
    expect(requestFullscreen).toHaveBeenCalledTimes(1);
  });

  it("returns false when fullscreen is unsupported", () => {
    window.Telegram = {
      WebApp: {
        initData: "query_id=test",
        ready: vi.fn(),
        expand: vi.fn(),
      },
    };

    expect(requestTelegramFullscreen()).toBe(false);
  });

  it("consumes Escape and dismisses the top internal layer", () => {
    const dismiss = document.createElement("button");
    const onDismiss = vi.fn();

    dismiss.setAttribute("data-escape-dismiss", "");
    dismiss.addEventListener("click", onDismiss);
    document.body.append(dismiss);

    const cleanup = bindDesktopEscapeGuard();
    const event = new KeyboardEvent("keydown", {
      key: "Escape",
      bubbles: true,
      cancelable: true,
    });

    window.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(onDismiss).toHaveBeenCalledTimes(1);

    cleanup();
    dismiss.remove();
  });

  it("subscribes and unsubscribes Telegram BackButton", () => {
    const handler = vi.fn();
    const backButton = {
      show: vi.fn(),
      hide: vi.fn(),
      onClick: vi.fn(),
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

    const cleanupBackButton = bindTelegramBackButton(true, handler);
    expect(backButton.show).toHaveBeenCalledTimes(1);
    expect(backButton.onClick).toHaveBeenCalledWith(handler);

    cleanupBackButton();
    expect(backButton.offClick).toHaveBeenCalledWith(handler);
    expect(backButton.hide).toHaveBeenCalledTimes(1);
  });
});
