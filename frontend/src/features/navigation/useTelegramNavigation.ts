import { useCallback, useEffect } from "react";
import {
  useLocation,
  useNavigate,
} from "react-router-dom";

import { bindTelegramBackButton } from "../../shared/telegram/webApp";

export function useInternalBackNavigation(): () => void {
  const location = useLocation();
  const navigate = useNavigate();

  return useCallback(() => {
    if (location.key !== "default") {
      navigate(-1);
      return;
    }
    navigate("/catalog", { replace: true });
  }, [location.key, navigate]);
}

export function useTelegramNavigation(): {
  showBack: boolean;
  navigateBack: () => void;
} {
  const location = useLocation();
  const showBack = location.pathname !== "/catalog";
  const navigateBack = useInternalBackNavigation();

  useEffect(
    () => bindTelegramBackButton(showBack, navigateBack),
    [navigateBack, showBack],
  );

  return { showBack, navigateBack };
}
