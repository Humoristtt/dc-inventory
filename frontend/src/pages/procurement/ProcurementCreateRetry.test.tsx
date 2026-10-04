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
  beforeEach,
  expect,
  it,
  vi,
} from "vitest";

import type {
  ProcurementLineInput,
} from "../../shared/api/procurement";
import { ProcurementCreatePage } from "./ProcurementCreatePage";

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  managers: vi.fn(),
}));

vi.mock(
  "../../features/auth/useAuthState",
  () => ({
    useAuthState: () => ({
      isPending: false,
      data: {
        user: {
          id: "retry-admin",
          telegram_user_id: 10001,
          username: "retry_user",
          first_name: "Retry",
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
    LineComposer: ({
      onChange,
    }: {
      lines: ProcurementLineInput[];
      onChange: (
        lines: ProcurementLineInput[],
      ) => void;
    }) => (
      <button
        type="button"
        onClick={() => {
          onChange([
            {
              line_type: "EXISTING_ITEM",
              item_id: "retry-item",
              display_name: "Retry item",
              quantity: 1,
            },
          ]);
        }}
      >
        ADD_RETRY_LINE
      </button>
    ),
  }),
);

vi.mock(
  "../../shared/api/procurement",
  async (importOriginal) => {
    const actual = await importOriginal<
      typeof import("../../shared/api/procurement")
    >();

    return {
      ...actual,
      createProcurementRequest: mocks.create,
      getProcurementManagers: mocks.managers,
    };
  },
);

function renderPage() {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
      mutations: {
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
          <Route
            path="/procurement/:requestId"
            element={
              <p>RETRY_DETAIL_DESTINATION</p>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mocks.create.mockReset();
  mocks.managers.mockReset();

  mocks.managers.mockResolvedValue({
    items: [
      {
        id: "retry-manager",
        display_name: "Менеджер повторной отправки",
      },
    ],
    total: 1,
    limit: 200,
    offset: 0,
  });

  mocks.create
    .mockRejectedValueOnce(
      new TypeError(
        "synthetic lost response after server commit",
      ),
    )
    .mockResolvedValueOnce({
      id: "retry-request",
    });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it(
  "повтор после потерянного ответа использует тот же client_request_id",
  async () => {
    renderPage();

    await screen.findByRole(
      "option",
      {
        name: "Менеджер повторной отправки",
      },
    );

    fireEvent.change(
      screen.getByLabelText("Менеджер"),
      {
        target: {
          value: "retry-manager",
        },
      },
    );

    fireEvent.click(
      screen.getByRole(
        "button",
        {
          name: "ADD_RETRY_LINE",
        },
      ),
    );

    fireEvent.click(
      screen.getByRole(
        "button",
        {
          name: "Отправить заявку",
        },
      ),
    );

    await waitFor(() => {
      expect(
        mocks.create,
      ).toHaveBeenCalledTimes(1);
    });

    await screen.findByRole("alert");

    fireEvent.click(
      screen.getByRole(
        "button",
        {
          name: "Отправить заявку",
        },
      ),
    );

    await waitFor(() => {
      expect(
        mocks.create,
      ).toHaveBeenCalledTimes(2);
    });

    const firstPayload = (
      mocks.create.mock.calls[0][0]
    ) as {
      client_request_id: string;
    };

    const retryPayload = (
      mocks.create.mock.calls[1][0]
    ) as {
      client_request_id: string;
    };

    expect(
      retryPayload.client_request_id,
    ).toBe(
      firstPayload.client_request_id,
    );
  },
);
