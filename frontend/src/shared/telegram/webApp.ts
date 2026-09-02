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

let sdkLoadPromise: Promise<void> | null = null;

export function getTelegramWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function loadTelegramWebAppSdk(): Promise<void> {
  if (getTelegramWebApp() !== null) {
    return Promise.resolve();
  }
  if (sdkLoadPromise !== null) {
    return sdkLoadPromise;
  }

  sdkLoadPromise = new Promise((resolve) => {
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${TELEGRAM_WEB_APP_SDK_PATH}"]`,
    );
    const script = existing ?? document.createElement("script");
    let settled = false;

    const finish = () => {
      if (settled) {
        return;
      }
      settled = true;
      resolve();
    };

    script.addEventListener("load", finish, { once: true });
    script.addEventListener("error", finish, { once: true });

    if (existing === null) {
      script.src = TELEGRAM_WEB_APP_SDK_PATH;
      script.async = true;
      document.head.append(script);
    }

    window.setTimeout(finish, 3_000);
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
