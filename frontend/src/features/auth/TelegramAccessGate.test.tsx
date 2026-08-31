import {
  cleanup,
  fireEvent,
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
import { TelegramAccessGate } from "./TelegramAccessGate";

const support = {
  username: "Humoristttt",
  url: "https://t.me/Humoristttt",
};

function renderGate() {
  render(
    <AppProviders>
      <TelegramAccessGate>
        <div>Каталог доступен</div>
      </TelegramAccessGate>
    </AppProviders>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete window.Telegram;
});

it("показывает приложение одобренному пользователю", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(
        JSON.stringify({
          user: {
            id: "00000000-0000-0000-0000-000000000001",
            telegram_user_id: 1001,
            username: "approved",
            first_name: "Approved",
            last_name: null,
            role: "USER",
            access_status: "APPROVED",
          },
          support,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ),
  );

  renderGate();

  expect(await screen.findByText("Каталог доступен")).toBeInTheDocument();
});

it("показывает контакт и создаёт запрос доступа", async () => {
  window.Telegram = {
    WebApp: {
      initData: "query_id=test&auth_date=1&hash=test",
      ready: vi.fn(),
      expand: vi.fn(),
      openTelegramLink: vi.fn(),
    },
  };

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url === "/api/auth/me") {
      return new Response(null, { status: 401 });
    }
    if (url === "/api/auth/telegram") {
      return new Response(
        JSON.stringify({
          user: {
            id: "00000000-0000-0000-0000-000000000002",
            telegram_user_id: 1002,
            username: "new-user",
            first_name: "New",
            last_name: null,
            role: "USER",
            access_status: "PENDING",
          },
          support,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (url === "/api/access-requests/me") {
      return new Response(
        JSON.stringify({ access_status: "PENDING", request: null }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (url === "/api/access-requests" && init?.method === "POST") {
      return new Response(
        JSON.stringify({
          access_status: "PENDING",
          request: {
            id: "00000000-0000-0000-0000-000000000010",
            status: "PENDING",
            requested_at: "2026-09-01T00:00:00Z",
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }

    throw new Error(`unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  renderGate();

  const supportLink = await screen.findByRole("link", { name: "@Humoristttt" });
  expect(supportLink).toHaveAttribute("href", "https://t.me/Humoristttt");

  fireEvent.click(screen.getByRole("button", { name: "ОК, запросить доступ" }));

  expect(await screen.findByRole("heading", { name: "Запрос отправлен" })).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/access-requests",
    expect.objectContaining({ method: "POST" }),
  );
});

it("пропускает пользователя, если access state уже стал APPROVED", async () => {
  window.Telegram = {
    WebApp: {
      initData: "query_id=test&auth_date=1&hash=test",
      ready: vi.fn(),
      expand: vi.fn(),
    },
  };

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/auth/me") {
        return new Response(
          JSON.stringify({
            user: {
              id: "00000000-0000-0000-0000-000000000003",
              telegram_user_id: 1003,
              username: "pending",
              first_name: "Pending",
              last_name: null,
              role: "USER",
              access_status: "PENDING",
            },
            support,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url === "/api/access-requests/me") {
        return new Response(
          JSON.stringify({ access_status: "APPROVED", request: null }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      throw new Error(`unexpected fetch: ${url}`);
    }),
  );

  renderGate();

  expect(await screen.findByText("Каталог доступен")).toBeInTheDocument();
});

it("позволяет повторно запросить доступ после отказа", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);

    if (url === "/api/auth/me") {
      return new Response(
        JSON.stringify({
          user: {
            id: "00000000-0000-0000-0000-000000000004",
            telegram_user_id: 1004,
            username: "rejected",
            first_name: "Rejected",
            last_name: null,
            role: "USER",
            access_status: "REJECTED",
          },
          support,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }

    if (url === "/api/access-requests" && init?.method === "POST") {
      return new Response(
        JSON.stringify({
          access_status: "PENDING",
          request: {
            id: "00000000-0000-0000-0000-000000000011",
            status: "PENDING",
            requested_at: "2026-09-01T01:00:00Z",
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }

    if (url === "/api/access-requests/me") {
      return new Response(
        JSON.stringify({
          access_status: "PENDING",
          request: {
            id: "00000000-0000-0000-0000-000000000011",
            status: "PENDING",
            requested_at: "2026-09-01T01:00:00Z",
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }

    throw new Error(`unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  renderGate();

  fireEvent.click(
    await screen.findByRole("button", { name: "Запросить доступ снова" }),
  );

  expect(
    await screen.findByRole("heading", { name: "Запрос отправлен" }),
  ).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/access-requests",
    expect.objectContaining({ method: "POST" }),
  );
});
