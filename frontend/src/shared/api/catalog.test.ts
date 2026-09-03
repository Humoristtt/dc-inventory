import {
  afterEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  encodeCatalogQuery,
  getCatalogItems,
} from "./catalog";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("catalog query encoding", () => {
  it("сохраняет буквальный поисковый запрос и same-origin session", async () => {
    const fetchMock = vi.fn(async (
      _input: RequestInfo | URL,
      _init?: RequestInit,
    ) => new Response(
      JSON.stringify({ items: [], total: 0, limit: 20, offset: 0 }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
    vi.stubGlobal("fetch", fetchMock);

    await getCatalogItems({ q: "  QSFP+ 100G / LR4  " });

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toContain("q=QSFP%2B+100G+%2F+LR4");
    expect(init).toEqual(expect.objectContaining({ credentials: "same-origin" }));
  });

  it("кодирует повторяющиеся exact-фильтры детерминированно", () => {
    const params = encodeCatalogQuery({
      category: "sfp",
      manufacturerIds: ["m-2", "m-1", "m-2"],
      filters: [
        { key: "speed", operator: "eq", value: "25G" },
        { key: "speed", operator: "eq", value: "10G" },
      ],
    });

    expect(params.get("category")).toBe("sfp");
    expect(params.getAll("manufacturer_id")).toEqual(["m-1", "m-2"]);
    expect(params.getAll("filter")).toEqual([
      "speed:eq:10G",
      "speed:eq:25G",
    ]);
  });

  it("кодирует границы range и сортировку детерминированно", () => {
    const params = encodeCatalogQuery({
      filters: [
        { key: "length", operator: "lte", value: "30.5" },
        { key: "length", operator: "gte", value: "2" },
      ],
      sort: "available",
      order: "desc",
    });

    expect(params.getAll("filter")).toEqual([
      "length:gte:2",
      "length:lte:30.5",
    ]);
    expect(params.get("sort")).toBe("available");
    expect(params.get("order")).toBe("desc");
  });
});
