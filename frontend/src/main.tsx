import "@fontsource-variable/inter";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { AppProviders } from "./app/providers/AppProviders";
import "./app/styles/tokens.css";
import "./app/styles/global.css";
import { TelegramAccessGate } from "./features/auth/TelegramAccessGate";
import { loadTelegramWebAppSdk } from "./shared/telegram/webApp";

const root = document.getElementById("root");

if (root === null) {
  throw new Error("Root element was not found");
}

const rootElement: HTMLElement = root;

function renderApplication() {
  createRoot(rootElement).render(
    <StrictMode>
      <AppProviders>
        <TelegramAccessGate>
          <App />
        </TelegramAccessGate>
      </AppProviders>
    </StrictMode>,
  );
}

void loadTelegramWebAppSdk().finally(renderApplication);
