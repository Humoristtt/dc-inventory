import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  MemoryRouter,
  Route,
  Routes,
} from "react-router-dom";
import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import { ProcurementCreatePage } from "./ProcurementCreatePage";

vi.mock(
  "../../features/auth/useAuthState",
  () => ({
    useAuthState: () => ({
      isPending: false,
      data: {
        user: {
          id: "cp05-admin",
          telegram_user_id: 50001,
          username: "cp05",
          first_name: "CP05",
          last_name: null,
          role: "ADMIN",
          access_status: "APPROVED",
          capabilities: [
            "procurement.create",
          ],
        },
        support: {
          username: "support",
          url: "https://t.me/support",
        },
      },
    }),
  }),
);

vi.mock(
  "../../features/procurement/LineComposer",
  () => ({
    LineComposer: () => null,
  }),
);

const managerRequests: string[] = [];

function jsonResponse(body: unknown): Response {
  return new Response(
    JSON.stringify(body),
    {
      status: 200,
      headers: {
        "Content-Type": "application/json",
      },
    },
  );
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[
          "/procurement/new",
        ]}
      >
        <Routes>
          <Route
            path="/procurement/new"
            element={
              <ProcurementCreatePage />
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  managerRequests.length = 0;
});

it(
  "manager lookup searches and paginates instead of truncating the candidate set",
  async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async (
          input: RequestInfo | URL,
        ) => {
          const url = String(input);

          if (
            !url.startsWith(
              "/api/procurement/managers?",
            )
          ) {
            throw new Error(
              `unexpected fetch ${url}`,
            );
          }

          managerRequests.push(url);

          const params = new URL(
            url,
            "http://test",
          ).searchParams;

          const query =
            params.get("q") ?? "";
          const limit = Number(
            params.get("limit")
            ?? "50",
          );
          const offset = Number(
            params.get("offset")
            ?? "0",
          );

          if (
            query === "Tail Manager"
          ) {
            return jsonResponse({
              items: [
                {
                  id: "manager-tail",
                  display_name:
                    "Tail Manager",
                },
              ],
              total: 1,
              limit,
              offset,
            });
          }

          const total = 205;
          const count = Math.max(
            0,
            Math.min(
              limit,
              total - offset,
            ),
          );

          return jsonResponse({
            items: Array.from(
              { length: count },
              (_, row) => {
                const position =
                  offset + row;

                return {
                  id:
                    `manager-${position}`,
                  display_name:
                    `Manager ${String(
                      position,
                    ).padStart(
                      3,
                      "0",
                    )}`,
                };
              },
            ),
            total,
            limit,
            offset,
          });
        },
      ),
    );

    renderPage();

    const search =
      await screen.findByLabelText(
        "Поиск менеджера",
      );

    const more =
      await screen.findByRole(
        "button",
        {
          name:
            /Показать ещё.*менедж/i,
        },
      );

    fireEvent.click(more);

    await waitFor(() => {
      expect(
        managerRequests.some(
          (requestUrl) =>
            Number(
              new URL(
                requestUrl,
                "http://test",
              ).searchParams.get(
                "offset",
              ) ?? "0",
            ) > 0,
        ),
      ).toBe(true);
    });

    fireEvent.change(
      search,
      {
        target: {
          value:
            "Tail Manager",
        },
      },
    );

    await waitFor(() => {
      expect(
        managerRequests.some(
          (requestUrl) =>
            new URL(
              requestUrl,
              "http://test",
            ).searchParams.get("q")
            === "Tail Manager",
        ),
      ).toBe(true);
    });

    expect(
      await screen.findByRole(
        "option",
        {
          name:
            "Tail Manager",
        },
      ),
    ).toBeTruthy();
  },
);
