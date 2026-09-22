import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { ProcurementLineInput } from "../../shared/api/procurement";
import { ProcurementCreatePage } from "./ProcurementCreatePage";

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  managers: vi.fn(),
}));

vi.mock("../../features/auth/useAuthState", () => ({
  useAuthState: () => ({
    isPending: false,
    data: {
      user: {
        id: "test-admin",
        role: "ADMIN",
        access_status: "APPROVED",
        capabilities: ["procurement.create"],
      },
    },
  }),
}));

vi.mock("../../features/procurement/LineComposer", () => ({
  LineComposer: ({ onChange }: {
    lines: ProcurementLineInput[];
    onChange: (lines: ProcurementLineInput[]) => void;
  }) => (
    <button
      type="button"
      onClick={() => onChange([{
        line_type: "EXISTING_ITEM",
        item_id: "test-item",
        display_name: "Test item",
        quantity: 1,
      }])}
    >
      ADD_TEST_LINE
    </button>
  ),
}));

vi.mock("../../shared/api/procurement", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../shared/api/procurement")>();
  return {
    ...actual,
    createProcurementRequest: mocks.create,
    getProcurementManagers: mocks.managers,
  };
});

beforeEach(() => {
  mocks.create.mockReset();
  mocks.managers.mockReset();
  mocks.managers.mockResolvedValue({
    items: [{ id: "test-manager", display_name: "Тестовый менеджер" }],
    total: 1,
    limit: 200,
    offset: 0,
  });
  mocks.create.mockRejectedValue(new TypeError("lost response after commit"));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("reuses the idempotency key on retry and rotates it when the payload changes", async () => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/procurement/new"]}>
        <Routes>
          <Route path="/procurement/new" element={<ProcurementCreatePage />} />
          <Route path="/procurement/:requestId" element={<p>CREATED</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  await screen.findByRole("option", { name: "Тестовый менеджер" });
  fireEvent.change(screen.getByLabelText("Менеджер"), {
    target: { value: "test-manager" },
  });
  fireEvent.click(screen.getByRole("button", { name: "ADD_TEST_LINE" }));

  const submit = screen.getByRole("button", { name: "Отправить заявку" });

  for (const count of [1, 2]) {
    fireEvent.click(submit);
    await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(count));
    await screen.findByRole("alert");
    await waitFor(() => expect(submit.hasAttribute("disabled")).toBe(false));
  }

  const first = mocks.create.mock.calls[0][0] as { client_request_id: string };
  const retry = mocks.create.mock.calls[1][0] as { client_request_id: string };
  expect(first.client_request_id).toBeTruthy();
  expect(retry.client_request_id).toBe(first.client_request_id);

  fireEvent.change(screen.getByLabelText("Общий комментарий"), {
    target: { value: "Новая редакция заявки" },
  });
  fireEvent.click(submit);
  await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(3));

  const changed = mocks.create.mock.calls[2][0] as { client_request_id: string };
  expect(changed.client_request_id).not.toBe(first.client_request_id);
});
