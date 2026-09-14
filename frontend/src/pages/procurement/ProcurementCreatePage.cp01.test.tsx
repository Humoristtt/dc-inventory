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
          id: "cp01-admin",
          telegram_user_id: 10001,
          username: "cp01",
          first_name: "CP01",
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
              item_id: "cp01-item",
              display_name: "CP01 item",
              quantity: 1,
            },
          ]);
        }}
      >
        ADD_CP01_LINE
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
              <p>CP01_DETAIL_DESTINATION</p>
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
        id: "cp01-manager",
        display_name: "Менеджер CP01",
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
      id: "cp01-request",
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
        name: "Менеджер CP01",
      },
    );

    fireEvent.change(
      screen.getByLabelText("Менеджер"),
      {
        target: {
          value: "cp01-manager",
        },
      },
    );

    fireEvent.click(
      screen.getByRole(
        "button",
        {
          name: "ADD_CP01_LINE",
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
