import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  afterEach,
  expect,
  it,
  vi,
} from "vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  TELEGRAM_WEB_APP_SDK_PATH,
  loadTelegramWebAppSdk,
} from "../../shared/telegram/webApp";
import { TelegramAccessGate } from "./TelegramAccessGate";

const support = {
  username: "Humoristttt",
  url: "https://t.me/Humoristttt",
};

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Number.POSITIVE_INFINITY,
        refetchOnWindowFocus: false,
      },
    },
  });
}

function renderGate(queryClient = createTestQueryClient()) {
  render(
    <QueryClientProvider client={queryClient}>
      <TelegramAccessGate>
        <div>Каталог доступен</div>
      </TelegramAccessGate>
    </QueryClientProvider>,
  );
  return queryClient;
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
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

it("периодически обновляет APPROVED auth state", async () => {
  vi.useFakeTimers();

  let authRequests = 0;

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url !== "/api/auth/me") {
        throw new Error(`unexpected fetch: ${url}`);
      }

      authRequests += 1;

      return new Response(
        JSON.stringify({
          user: {
            id: "00000000-0000-0000-0000-000000000009",
            telegram_user_id: 1009,
            username: "refresh-user",
            first_name: "Refresh",
            last_name: null,
            role: "USER",
            access_status:
              authRequests === 1
                ? "APPROVED"
                : "BLOCKED",
          },
          support,
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      );
    }),
  );

  renderGate();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });

  expect(
    screen.getByText("Каталог доступен"),
  ).toBeInTheDocument();

  expect(authRequests).toBe(1);

  await act(async () => {
    await vi.advanceTimersByTimeAsync(60_000);
  });

  expect(authRequests).toBe(2);
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

it("свежий BLOCKED из auth не затирается старым APPROVED access cache", async () => {
  const userId = "00000000-0000-0000-0000-000000000005";
  const queryClient = createTestQueryClient();

  queryClient.setQueryData(["auth", "state"], {
    user: {
      id: userId,
      telegram_user_id: 1005,
      username: "transition",
      first_name: "Transition",
      last_name: null,
      role: "USER",
      access_status: "PENDING",
    },
    support,
  });
  queryClient.setQueryData(["access", "me", userId], {
    access_status: "APPROVED",
    request: null,
  });

  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new Error("unexpected fetch");
    }),
  );

  renderGate(queryClient);
  expect(await screen.findByText("Каталог доступен")).toBeInTheDocument();

  await act(async () => {
    queryClient.setQueryData(["auth", "state"], {
      user: {
        id: userId,
        telegram_user_id: 1005,
        username: "transition",
        first_name: "Transition",
        last_name: null,
        role: "USER",
        access_status: "BLOCKED",
      },
      support,
    });
  });

  expect(
    await screen.findByRole("heading", { name: "Доступ ограничен" }),
  ).toBeInTheDocument();
  expect(screen.queryByText("Каталог доступен")).not.toBeInTheDocument();
});

it("access cache одного пользователя не применяется к другому", async () => {
  const secondUserId = "00000000-0000-0000-0000-000000000006";
  const queryClient = createTestQueryClient();

  queryClient.setQueryData(["auth", "state"], {
    user: {
      id: secondUserId,
      telegram_user_id: 1006,
      username: "second",
      first_name: "Second",
      last_name: null,
      role: "USER",
      access_status: "PENDING",
    },
    support,
  });

  queryClient.setQueryData(["access", "me"], {
    access_status: "APPROVED",
    request: null,
  });

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/access-requests/me") {
        return new Response(
          JSON.stringify({
            access_status: "PENDING",
            request: {
              id: "00000000-0000-0000-0000-000000000012",
              status: "PENDING",
              requested_at: "2026-09-01T02:00:00Z",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`unexpected fetch: ${url}`);
    }),
  );

  renderGate(queryClient);

  expect(
    await screen.findByRole("heading", { name: "Запрос отправлен" }),
  ).toBeInTheDocument();
  expect(screen.queryByText("Каталог доступен")).not.toBeInTheDocument();
});

it("late PENDING request response не понижает свежий APPROVED auth state", async () => {
  const userId = "00000000-0000-0000-0000-000000000007";
  const queryClient = createTestQueryClient();
  let resolveRequest: ((response: Response) => void) | undefined;
  const requestResponse = new Promise<Response>((resolve) => {
    resolveRequest = resolve;
  });

  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/auth/me") {
        return new Response(
          JSON.stringify({
            user: {
              id: userId,
              telegram_user_id: 1007,
              username: "late-response",
              first_name: "Late",
              last_name: null,
              role: "USER",
              access_status: "REJECTED",
            },
            support,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (
        url === "/api/access-requests"
        && init?.method === "POST"
      ) {
        return requestResponse;
      }

      throw new Error(`unexpected fetch: ${url}`);
    },
  );
  vi.stubGlobal("fetch", fetchMock);

  renderGate(queryClient);

  fireEvent.click(
    await screen.findByRole(
      "button",
      { name: "Запросить доступ снова" },
    ),
  );

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/access-requests",
      expect.objectContaining({ method: "POST" }),
    );
  });

  await act(async () => {
    queryClient.setQueryData(["auth", "state"], {
      user: {
        id: userId,
        telegram_user_id: 1007,
        username: "late-response",
        first_name: "Late",
        last_name: null,
        role: "USER",
        access_status: "APPROVED",
      },
      support,
    });
  });

  expect(await screen.findByText("Каталог доступен")).toBeInTheDocument();

  const completeRequest = resolveRequest;
  if (completeRequest === undefined) {
    throw new Error("request resolver was not initialized");
  }

  await act(async () => {
    completeRequest(
      new Response(
        JSON.stringify({
          access_status: "PENDING",
          request: {
            id: "00000000-0000-0000-0000-000000000013",
            status: "PENDING",
            requested_at: "2026-09-01T07:00:00Z",
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    await requestResponse;
  });

  expect(await screen.findByText("Каталог доступен")).toBeInTheDocument();
});

it("повторно загружает Telegram SDK после ошибки и восстанавливает auth", async () => {
  const ready = vi.fn();
  const expand = vi.fn();
  let authMeCalls = 0;

  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);

    if (url === "/api/auth/me") {
      authMeCalls += 1;
      return new Response(null, { status: 401 });
    }

    if (url === "/api/auth/telegram") {
      return new Response(
        JSON.stringify({
          user: {
            id: "00000000-0000-0000-0000-000000000008",
            telegram_user_id: 1008,
            username: "sdk-recovered",
            first_name: "Recovered",
            last_name: null,
            role: "USER",
            access_status: "APPROVED",
          },
          support,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    throw new Error(`unexpected fetch: ${url}`);
  });

  vi.stubGlobal("fetch", fetchMock);

  const firstSdkPromise = loadTelegramWebAppSdk();

  const firstScript =
    document.querySelector<HTMLScriptElement>(
      `script[src="${TELEGRAM_WEB_APP_SDK_PATH}"]`,
    );

  expect(firstScript).not.toBeNull();

  firstScript?.dispatchEvent(new Event("error"));
  await firstSdkPromise;

  expect(
    document.querySelector(
      `script[src="${TELEGRAM_WEB_APP_SDK_PATH}"]`,
    ),
  ).toBeNull();

  renderGate();

  expect(
    await screen.findByRole(
      "heading",
      { name: "Не удалось загрузить Telegram" },
    ),
  ).toBeInTheDocument();

  expect(
    screen.queryByRole(
      "heading",
      { name: "Откройте приложение через Telegram" },
    ),
  ).not.toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("button", { name: "Повторить" }),
  );

  const retryScript = await waitFor(() => {
    const script =
      document.querySelector<HTMLScriptElement>(
        `script[src="${TELEGRAM_WEB_APP_SDK_PATH}"]`,
      );

    if (script === null) {
      throw new Error("retry Telegram SDK script was not mounted");
    }

    return script;
  });

  expect(retryScript).not.toBe(firstScript);

  window.Telegram = {
    WebApp: {
      initData: "query_id=recovered&auth_date=1&hash=recovered",
      ready,
      expand,
    },
  };

  retryScript?.dispatchEvent(new Event("load"));

  expect(
    await screen.findByText("Каталог доступен"),
  ).toBeInTheDocument();

  expect(authMeCalls).toBeGreaterThanOrEqual(2);
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/auth/telegram",
    expect.objectContaining({ method: "POST" }),
  );
  expect(ready).toHaveBeenCalledTimes(1);
  expect(expand).toHaveBeenCalledTimes(1);
});
