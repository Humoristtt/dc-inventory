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
  ProcurementRequest,
} from "../../shared/api/procurement";
import { ItemFormPage } from "./ItemFormPage";

const mocks = vi.hoisted(() => ({
  createAndBind: vi.fn(),
  procurement: vi.fn(),
  categories: vi.fn(),
  category: vi.fn(),
  items: vi.fn(),
  manufacturers: vi.fn(),
}));

vi.mock(
  "../../features/auth/useAuthState",
  () => ({
    useAuthState: () => ({
      isPending: false,
      data: {
        user: {
          id: "test-senior",
          telegram_user_id: 7001,
          username: "senior",
          first_name: "Senior",
          last_name: null,
          role: "SENIOR_ENGINEER",
          access_status: "APPROVED",
          capabilities: [
            "catalog.read",
            "catalog.manage",
            "procurement.read",
            "procurement.accept",
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
  "../../features/navigation/useTelegramNavigation",
  () => ({
    useInternalBackNavigation: () => vi.fn(),
  }),
);

vi.mock(
  "../../shared/telegram/useTelegramWebApp",
  () => ({
    useTelegramWebApp: () => null,
  }),
);

vi.mock(
  "../../shared/api/procurement",
  async (importOriginal) => {
    const actual =
      await importOriginal<
        typeof import("../../shared/api/procurement")
      >();

    return {
      ...actual,
      createAndBindProcurementLine:
        mocks.createAndBind,
      getProcurementRequest:
        mocks.procurement,
    };
  },
);

vi.mock(
  "../../shared/api/catalog",
  async (importOriginal) => {
    const actual =
      await importOriginal<
        typeof import("../../shared/api/catalog")
      >();

    return {
      ...actual,
      getCatalogCategories:
        mocks.categories,
      getCatalogCategory:
        mocks.category,
      getCatalogItems:
        mocks.items,
      getCatalogManufacturers:
        mocks.manufacturers,
    };
  },
);

const request: ProcurementRequest = {
  id: "request-1",
  request_number: "PR-2026-0702",
  status: "PURCHASING",
  status_label: "В закупке",
  initiator: {
    id: "user-admin",
    display_name: "Admin",
  },
  assigned_manager: {
    id: "user-manager",
    display_name: "Manager",
  },
  current_revision_id: "revision-1",
  revision_number: 1,
  line_count: 1,
  state_version: 4,
  created_at: "2026-09-30T00:00:00Z",
  updated_at: "2026-09-30T00:00:00Z",
  completed_at: null,
  current_revision: {
    id: "revision-1",
    revision_number: 1,
    submitted_by: {
      id: "user-admin",
      display_name: "Admin",
    },
    general_comment: null,
    created_at: "2026-09-30T00:00:00Z",
    lines: [
      {
        id: "line-1",
        line_no: 1,
        line_type: "PROPOSED_ITEM",
        catalog_item_id: null,
        bound_item_id: null,
        display_snapshot: {
          category_key: "optical_patch_cord",
          category_name: "Оптические патч-корды",
          manufacturer_id: null,
          manufacturer_name: null,
          name: "Synthetic cable",
          model: null,
          attributes: {},
        },
        quantity: 1,
      },
    ],
  },
  revisions: [],
  events: [],
  final_movement_id: null,
  available_actions: ["bind_lines"],
};

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
          "/catalog/new?procurementRequestId=request-1&procurementLineId=line-1",
        ]}
      >
        <Routes>
          <Route
            path="/catalog/new"
            element={<ItemFormPage />}
          />
          <Route
            path="/procurement/:requestId"
            element={<p>PROCUREMENT_DESTINATION</p>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mocks.createAndBind.mockReset();
  mocks.procurement.mockReset();
  mocks.categories.mockReset();
  mocks.category.mockReset();
  mocks.items.mockReset();
  mocks.manufacturers.mockReset();

  mocks.procurement.mockResolvedValue(request);
  mocks.categories.mockResolvedValue([
    {
      id: "family-optics",
      key: "optics",
      display_name: "Оптика",
      description: null,
      sort_order: 10,
      is_system: true,
      parent_id: null,
    },
    {
      id: "category-patch-cord",
      key: "optical_patch_cord",
      display_name: "Оптические патч-корды",
      description: null,
      sort_order: 10,
      is_system: true,
      parent_id: "family-optics",
    },
  ]);
  mocks.category.mockResolvedValue({
    id: "category-patch-cord",
    key: "optical_patch_cord",
    display_name: "Оптические патч-корды",
    description: null,
    sort_order: 10,
    is_system: true,
    parent_id: "family-optics",
    attributes: [],
  });
  mocks.items.mockResolvedValue({
    items: [],
    total: 0,
    limit: 8,
    offset: 0,
  });
  mocks.manufacturers.mockResolvedValue({
    items: [],
    total: 0,
    limit: 8,
    offset: 0,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it(
  "reuses proposed-bind idempotency key after a lost response and rotates it for changed payload",
  async () => {
    mocks.createAndBind
      .mockRejectedValueOnce(
        new TypeError(
          "lost response after commit",
        ),
      )
      .mockRejectedValueOnce(
        new TypeError(
          "lost response after commit",
        ),
      )
      .mockResolvedValueOnce({
        ...request,
        current_revision: {
          ...request.current_revision,
          lines: [
            {
              ...request.current_revision.lines[0],
              bound_item_id: "item-created",
            },
          ],
        },
      });

    renderPage();

    const submit =
      await screen.findByRole(
        "button",
        {
          name: "Сохранить",
        },
      );

    await waitFor(() => {
      expect(
        (submit as HTMLButtonElement).disabled,
      ).toBe(false);
    });

    for (const count of [1, 2]) {
      fireEvent.click(submit);

      await waitFor(() => {
        expect(
          mocks.createAndBind,
        ).toHaveBeenCalledTimes(count);
      });

      await screen.findByRole("alert");

      await waitFor(() => {
        expect(
          (submit as HTMLButtonElement).disabled,
        ).toBe(false);
      });
    }

    const firstKey =
      mocks.createAndBind.mock.calls[0][3];
    const retryKey =
      mocks.createAndBind.mock.calls[1][3];

    expect(firstKey).toBeTruthy();
    expect(retryKey).toBe(firstKey);

    fireEvent.change(
      screen.getByLabelText(
        "Название оборудования",
      ),
      {
        target: {
          value:
            "Changed synthetic cable",
        },
      },
    );

    fireEvent.click(submit);

    await waitFor(() => {
      expect(
        mocks.createAndBind,
      ).toHaveBeenCalledTimes(3);
    });

    const changedKey =
      mocks.createAndBind.mock.calls[2][3];

    expect(changedKey).toBeTruthy();
    expect(changedKey).not.toBe(firstKey);
  },
);

it(
  "submits proposed bind at most once while a request is pending",
  async () => {
    let resolveMutation:
      | ((value: ProcurementRequest) => void)
      | undefined;

    mocks.createAndBind.mockImplementation(
      () =>
        new Promise<ProcurementRequest>(
          (resolve) => {
            resolveMutation = resolve;
          },
        ),
    );

    renderPage();

    const submit =
      await screen.findByRole(
        "button",
        {
          name: "Сохранить",
        },
      );

    await waitFor(() => {
      expect(
        (submit as HTMLButtonElement).disabled,
      ).toBe(false);
    });

    fireEvent.click(submit);
    fireEvent.click(submit);

    await waitFor(() => {
      expect(
        mocks.createAndBind,
      ).toHaveBeenCalledTimes(1);
    });

    expect(
      (submit as HTMLButtonElement).disabled,
    ).toBe(true);

    resolveMutation?.(request);
  },
);
