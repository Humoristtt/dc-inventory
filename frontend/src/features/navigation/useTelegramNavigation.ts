import { useCallback, useEffect } from "react";
import {
  useLocation,
  useNavigate,
} from "react-router-dom";

import { APP_DEFAULT_PATH } from "../../app/appRoutes";
import { bindTelegramBackButton } from "../../shared/telegram/webApp";

import { useTelegramWebApp } from "../../shared/telegram/useTelegramWebApp";

export function useInternalBackNavigation(): () => void {
  const location = useLocation();
  const navigate = useNavigate();

  return useCallback(() => {
    if (location.key !== "default") {
      navigate(-1);
      return;
    }
    navigate(APP_DEFAULT_PATH, { replace: true });
  }, [location.key, navigate]);
}

export function useTelegramNavigation(): {
  showBack: boolean;
  navigateBack: () => void;
} {
  const location = useLocation();
  const webApp = useTelegramWebApp();
  const showBack = location.pathname !== APP_DEFAULT_PATH;
  const navigateBack = useInternalBackNavigation();

  useEffect(
    () => bindTelegramBackButton(showBack, navigateBack),
    [navigateBack, showBack, webApp],
  );

  return { showBack, navigateBack };
}
