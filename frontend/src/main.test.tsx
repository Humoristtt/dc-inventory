import { expect, it, vi } from "vitest";

const render = vi.hoisted(() => vi.fn());
vi.mock("react-dom/client", () => ({ createRoot: () => ({ render }) }));
vi.mock("./shared/telegram/webApp", async (original) => ({
  ...await original<object>(),
  loadTelegramWebAppSdk: () => new Promise(() => {}),
}));

it("submits the React tree without waiting for the SDK promise", async () => {
  document.body.innerHTML = '<div id="root"></div>';
  await import("./main");
  expect(render).toHaveBeenCalledTimes(1);
});
