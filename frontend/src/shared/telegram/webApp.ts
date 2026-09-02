type TelegramWebApp = {
  initData: string;
  ready: () => void;
  expand: () => void;
  openTelegramLink?: (url: string) => void;
};

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
  }
}

export const TELEGRAM_WEB_APP_SDK_PATH =
  "/vendor/telegram/telegram-web-app.js";

export type TelegramWebAppSdkLoadStatus =
  | "idle"
  | "loading"
  | "ready"
  | "load-error"
  | "timeout";

let sdkLoadPromise: Promise<void> | null = null;
let sdkLoadStatus: TelegramWebAppSdkLoadStatus = "idle";

export function getTelegramWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function getTelegramWebAppSdkLoadStatus():
  TelegramWebAppSdkLoadStatus {
  if (getTelegramWebApp() !== null) {
    return "ready";
  }
  return sdkLoadStatus;
}

export function loadTelegramWebAppSdk(): Promise<void> {
  if (getTelegramWebApp() !== null) {
    sdkLoadStatus = "ready";
    return Promise.resolve();
  }

  if (sdkLoadPromise !== null) {
    return sdkLoadPromise;
  }

  sdkLoadStatus = "loading";

  sdkLoadPromise = new Promise((resolve) => {
    const existing =
      document.querySelector<HTMLScriptElement>(
        `script[src="${TELEGRAM_WEB_APP_SDK_PATH}"]`,
      );

    const script =
      existing ?? document.createElement("script");

    let settled = false;
    let timeoutId: number | null = null;

    const finish = (
      status: TelegramWebAppSdkLoadStatus,
    ) => {
      if (settled) {
        return;
      }

      settled = true;
      sdkLoadStatus = status;

      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }

      if (status !== "ready") {
        script.remove();
        sdkLoadPromise = null;
      }

      resolve();
    };

    script.addEventListener(
      "load",
      () => {
        finish(
          getTelegramWebApp() === null
            ? "load-error"
            : "ready",
        );
      },
      { once: true },
    );

    script.addEventListener(
      "error",
      () => {
        finish("load-error");
      },
      { once: true },
    );

    if (existing === null) {
      script.src = TELEGRAM_WEB_APP_SDK_PATH;
      script.async = true;
      document.head.append(script);
    }

    timeoutId = window.setTimeout(
      () => {
        finish("timeout");
      },
      3_000,
    );
  });

  return sdkLoadPromise;
}

export function prepareTelegramWebApp(): TelegramWebApp | null {
  const webApp = getTelegramWebApp();
  webApp?.ready();
  webApp?.expand();
  return webApp;
}

export function getTelegramInitData(): string {
  return getTelegramWebApp()?.initData.trim() ?? "";
}

export function openTelegramContact(url: string): boolean {
  const webApp = getTelegramWebApp();
  if (webApp?.openTelegramLink === undefined) {
    return false;
  }
  webApp.openTelegramLink(url);
  return true;
}
