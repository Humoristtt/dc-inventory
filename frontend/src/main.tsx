import "@fontsource-variable/inter";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { AppProviders } from "./app/providers/AppProviders";
import { preloadRouteForPath } from "./app/routeModules";
import "./app/styles/tokens.css";
import "./app/styles/global.css";
import { TelegramAccessGate } from "./features/auth/TelegramAccessGate";

const root = document.getElementById("root");

if (root === null) {
  throw new Error("Root element was not found");
}

const rootElement: HTMLElement = root;

// Start downloading the requested route while cookie-session authentication
// is still in flight. Loading code does not bypass the access gate or expose
// protected API data.
void preloadRouteForPath(window.location.pathname);

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

renderApplication();
