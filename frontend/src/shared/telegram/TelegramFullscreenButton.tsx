import {
  getTelegramWebApp,
  requestTelegramFullscreen,
} from "./webApp";

export function TelegramFullscreenButton() {
  if (getTelegramWebApp()?.requestFullscreen === undefined) {
    return null;
  }

  return (
    <button
      aria-label="Открыть на полный экран"
      className="telegram-fullscreen-button"
      onClick={() => {
        requestTelegramFullscreen();
      }}
      title="Открыть на полный экран"
      type="button"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
      >
        <path
          d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2"
        />
      </svg>
      <span>На весь экран</span>
    </button>
  );
}
