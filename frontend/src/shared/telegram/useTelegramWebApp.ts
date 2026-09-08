import { useSyncExternalStore } from "react";

import {
  getTelegramWebApp,
  getTelegramWebAppSdkLoadStatus,
  subscribeTelegramSdk,
} from "./webApp";

export function useTelegramWebApp() {
  useSyncExternalStore(subscribeTelegramSdk, getTelegramWebAppSdkLoadStatus);
  return getTelegramWebApp();
}
