import {
  useEffect,
  useState,
} from "react";

import {
  exitTelegramFullscreen,
  getTelegramWebApp,
  requestTelegramFullscreen,
} from "./webApp";

export function TelegramFullscreenButton() {
  const webApp = getTelegramWebApp();

  const [fullscreen, setFullscreen] = useState(
    () => webApp?.isFullscreen === true,
  );

  useEffect(() => {
    if (webApp === null) {
      return;
    }

    const syncFullscreen = () => {
      setFullscreen(webApp.isFullscreen === true);
    };

    syncFullscreen();

    webApp.onEvent?.(
      "fullscreenChanged",
      syncFullscreen,
    );

    return () => {
      webApp.offEvent?.(
        "fullscreenChanged",
        syncFullscreen,
      );
    };
  }, [webApp]);

  if (
    webApp?.requestFullscreen === undefined
    || webApp.exitFullscreen === undefined
  ) {
    return null;
  }

  const label = fullscreen
    ? "Выйти из полного экрана"
    : "На весь экран";

  return (
    <button
      aria-label={label}
      className="telegram-fullscreen-button"
      onClick={() => {
        if (fullscreen) {
          exitTelegramFullscreen();
          return;
        }

        requestTelegramFullscreen();
      }}
      title={label}
      type="button"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
      >
        {fullscreen ? (
          <path
            d="M9 9H4V4M15 9h5V4M9 15H4v5M15 15h5v5"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
          />
        ) : (
          <path
            d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"
            fill="none"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
          />
        )}
      </svg>

      <span>{label}</span>
    </button>
  );
}
