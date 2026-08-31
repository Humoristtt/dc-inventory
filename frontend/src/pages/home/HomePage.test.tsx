import {
  render,
  screen,
} from "@testing-library/react";
import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import { AppProviders } from "../../app/providers/AppProviders";
import { HomePage } from "./HomePage";

afterEach(() => {
  vi.unstubAllGlobals();
});

it("показывает готовность backend", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(
        JSON.stringify({ status: "ready" }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    ),
  );

  render(
    <AppProviders>
      <HomePage />
    </AppProviders>,
  );

  expect(
    screen.getByRole("heading", {
      name: "Оборудование — под контролем.",
    }),
  ).toBeInTheDocument();

  expect(
    await screen.findByText("Система готова"),
  ).toBeInTheDocument();
});
