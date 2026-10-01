import { Button, Input, Select } from "../../shared/ui";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { AttributeControl } from "../catalog/AttributeControl";
import {
  validateDraftAttributes,
  type AttributeDraft,
} from "../catalog/itemForm";
import {
  getCatalogCategories,
  getCatalogCategory,
  getCatalogItems,
  getCatalogManufacturers,
} from "../../shared/api/catalog";
import {
  catalogItemLabel,
  fuzzyScore,
} from "./catalogItemSearch";
import type { ProcurementLineInput } from "../../shared/api/procurement";

const MAX_PROCUREMENT_LINES = 500;

function quantity(value: string): number | null {
  if (!/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function lineLabel(line: ProcurementLineInput): string {
  if (line.line_type === "EXISTING_ITEM") {
    return line.display_name ?? `Карточка ${line.item_id}`;
  }
  return [line.name, line.model].filter(Boolean).join(" · ");
}

type Props = {
  lines: ProcurementLineInput[];
  onChange: (lines: ProcurementLineInput[]) => void;
};

export function LineComposer({ lines, onChange }: Props) {
  const [mode, setMode] = useState<"EXISTING_ITEM" | "PROPOSED_ITEM">(
    "EXISTING_ITEM",
  );
  const [search, setSearch] = useState("");
  const [catalogCategory, setCatalogCategory] = useState("");
  const [existingItemId, setExistingItemId] = useState("");
  const [qty, setQty] = useState("1");
  const [category, setCategory] = useState("");
  const [manufacturerId, setManufacturerId] = useState("");
  const [manufacturerSearch, setManufacturerSearch] = useState("");
  const [name, setName] = useState("");
  const [model, setModel] = useState("");
  const [attributes, setAttributes] = useState<AttributeDraft>({});
  const [error, setError] = useState("");

  const categories = useQuery({
    queryKey: ["catalog", "categories"],
    queryFn: ({ signal }) => getCatalogCategories(signal),
    staleTime: 5 * 60_000,
  });
  const leaves = useMemo(() => {
    const all = categories.data ?? [];
    const parents = new Set(all.map((entry) => entry.parent_id).filter(Boolean));
    return all.filter((entry) => !parents.has(entry.id));
  }, [categories.data]);

  const selectedProposedCategory = leaves.find(
    (entry) => entry.key === category,
  );
  const identityRequired =
    selectedProposedCategory?.requires_manufacturer_model === true;

  const categoryGroups = useMemo(() => {
    const all = categories.data ?? [];
    const families = all
      .filter((entry) => entry.parent_id === null)
      .sort(
        (left, right) =>
          left.sort_order - right.sort_order
          || left.display_name.localeCompare(right.display_name, "ru"),
      );

    return families.map((family) => ({
      family,
      children: all
        .filter((entry) => entry.parent_id === family.id)
        .sort(
          (left, right) =>
            left.sort_order - right.sort_order
            || left.display_name.localeCompare(right.display_name, "ru"),
        ),
    }));
  }, [categories.data]);
  const schema = useQuery({
    queryKey: ["catalog", "category", category],
    queryFn: ({ signal }) => getCatalogCategory(category, signal),
    enabled: Boolean(category),
    staleTime: 5 * 60_000,
  });
  const manufacturers = useInfiniteQuery({
    queryKey: [
      "catalog",
      "manufacturers",
      "procurement",
      manufacturerSearch,
    ],
    queryFn: ({ pageParam, signal }) =>
      getCatalogManufacturers(
        {
          q: manufacturerSearch,
          limit: 50,
          offset: pageParam,
        },
        signal,
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const nextOffset =
        lastPage.offset
        + lastPage.items.length;

      return nextOffset < lastPage.total
        ? nextOffset
        : undefined;
    },
    enabled:
      mode === "PROPOSED_ITEM"
      && identityRequired,
    staleTime: 5 * 60_000,
  });

  const manufacturerOptions =
    manufacturers.data?.pages.flatMap(
      (page) => page.items,
    )
    ?? [];

  const browseItems = useInfiniteQuery({
    queryKey: [
      "catalog",
      "procurement-browse",
      catalogCategory,
    ],
    queryFn: ({ pageParam, signal }) =>
      getCatalogItems(
        {
          category: catalogCategory || undefined,
          limit: 100,
          offset: pageParam,
          sort: "name",
          order: "asc",
        },
        signal,
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const nextOffset =
        lastPage.offset
        + lastPage.items.length;

      return nextOffset < lastPage.total
        ? nextOffset
        : undefined;
    },
    enabled: mode === "EXISTING_ITEM",
    staleTime: 60_000,
  });

  const searchItems = useInfiniteQuery({
    queryKey: [
      "catalog",
      "procurement-search",
      catalogCategory,
      search,
    ],
    queryFn: ({ pageParam, signal }) =>
      getCatalogItems(
        {
          q: search,
          category: catalogCategory || undefined,
          limit: 20,
          offset: pageParam,
          sort: "relevance",
          order: "desc",
        },
        signal,
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const nextOffset =
        lastPage.offset
        + lastPage.items.length;

      return nextOffset < lastPage.total
        ? nextOffset
        : undefined;
    },
    enabled:
      mode === "EXISTING_ITEM"
      && search.trim().length >= 2,
  });

  const browseOptions = useMemo(
    () =>
      browseItems.data?.pages.flatMap(
        (page) => page.items,
      ) ?? [],
    [browseItems.data?.pages],
  );

  const serverSearchOptions = useMemo(
    () =>
      searchItems.data?.pages.flatMap(
        (page) => page.items,
      ) ?? [],
    [searchItems.data?.pages],
  );

  const itemOptions = useMemo(() => {
    const query = search.trim();

    if (query.length < 2) {
      return browseOptions;
    }

    const seen = new Set(
      serverSearchOptions.map((item) => item.id),
    );

    const fuzzy = browseOptions
      .map((item) => ({
        item,
        score: fuzzyScore(item, query),
      }))
      .filter(({ item, score }) =>
        !seen.has(item.id) && score >= 0.42,
      )
      .sort(
        (left, right) =>
          right.score - left.score
          || catalogItemLabel(left.item).localeCompare(
            catalogItemLabel(right.item),
            "ru",
          ),
      )
      .map(({ item }) => item);

    return [
      ...serverSearchOptions,
      ...fuzzy,
    ];
  }, [
    browseOptions,
    search,
    serverSearchOptions,
  ]);

  const activeItemsQuery =
    search.trim().length >= 2
      ? searchItems
      : browseItems;


  const add = () => {
    if (lines.length >= MAX_PROCUREMENT_LINES) {
      setError("В одной заявке может быть не более 500 позиций.");
      return;
    }
    const amount = quantity(qty);
    if (amount === null) {
      setError("Количество должно быть положительным целым числом.");
      return;
    }
    if (mode === "EXISTING_ITEM") {
      if (!existingItemId) {
        setError("Выберите позицию каталога.");
        return;
      }
      const selectedItem = itemOptions.find(
        (item) => item.id === existingItemId,
      );
      const displayName = selectedItem
        ? [selectedItem.manufacturer?.name, selectedItem.name, selectedItem.model]
            .filter(Boolean)
            .join(" · ")
        : undefined;
      onChange([
        ...lines,
        {
          line_type: "EXISTING_ITEM",
          item_id: existingItemId,
          display_name: displayName,
          quantity: amount,
        },
      ]);
      setExistingItemId("");
      setSearch("");
      setQty("1");
      setError("");
      return;
    }
    const definitions =
      schema.data?.attributes.filter((entry) => entry.key !== "reach_m") ?? [];
    const validation = validateDraftAttributes(definitions, attributes);
    if (!category || !name.trim() || Object.keys(validation.errors).length) {
      setError("Заполните категорию, название и обязательные характеристики.");
      return;
    }
    if (identityRequired && (!manufacturerId || !model.trim())) {
      setError("Для этой категории нужны производитель и модель.");
      return;
    }
    onChange([
      ...lines,
      {
        line_type: "PROPOSED_ITEM",
        category_key: category,
        manufacturer_id: manufacturerId || null,
        name: name.trim(),
        model: model.trim() || null,
        attributes: validation.values,
        quantity: amount,
      },
    ]);
    setName("");
    setModel("");
    setAttributes({});
    setQty("1");
    setError("");
  };

  return (
    <section className="detail-panel procurement-composer">
      <h2>Состав</h2>
      {lines.length ? (
        <ol className="procurement-lines">
          {lines.map((line, index) => (
            <li key={`${lineLabel(line)}-${index}`}>
              <span>
                {lineLabel(line)} — {line.quantity} шт.
              </span>
              <Button
                className="button button--ghost"
                onClick={() => onChange(lines.filter((_, row) => row !== index))}
                type="button"
              >
                Удалить
              </Button>
            </li>
          ))}
        </ol>
      ) : (
        <p className="empty-state">Добавьте хотя бы одну позицию.</p>
      )}

      <div className="procurement-mode" role="group" aria-label="Тип позиции">
        <Button
          className={mode === "EXISTING_ITEM" ? "button button--dark" : "button"}
          onClick={() => setMode("EXISTING_ITEM")}
          type="button"
        >
          Из каталога
        </Button>
        <Button
          className={mode === "PROPOSED_ITEM" ? "button button--dark" : "button"}
          onClick={() => setMode("PROPOSED_ITEM")}
          type="button"
        >
          Новая позиция
        </Button>
      </div>

      {mode === "EXISTING_ITEM" ? (
        <div className="procurement-fields">
          <label>
            Категория
            <Select
              value={catalogCategory}
              onChange={(event) => {
                setCatalogCategory(event.target.value);
                setExistingItemId("");
              }}
            >
              <option value="">Все категории и подкатегории</option>
              {categoryGroups.map(({ family, children }) => (
                <optgroup key={family.id} label={family.display_name}>
                  <option value={family.key}>
                    Все: {family.display_name}
                  </option>
                  {children.map((entry) => (
                    <option key={entry.id} value={entry.key}>
                      {entry.display_name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </label>

          <label>
            Поиск по каталогу
            <Input
              autoCapitalize="none"
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setExistingItemId("");
              }}
            />
          </label>

          <label>
            Позиция
            <Select
              value={existingItemId}
              onChange={(event) => setExistingItemId(event.target.value)}
            >
              <option value="">
                {browseItems.isPending
                  ? "Загружаем каталог…"
                  : "Выберите"}
              </option>
              {itemOptions.map((item) => (
                <option
                  key={item.id}
                  value={item.id}
                >
                  {catalogItemLabel(item)}
                </option>
              ))}
            </Select>
          </label>

          {search.trim().length >= 2
            && !searchItems.isFetching
            && itemOptions.length === 0 ? (
              <p className="empty-state">
                Совпадений и похожих позиций не найдено.
              </p>
            ) : null}

          {activeItemsQuery.hasNextPage ? (
            <Button
              className="button button--load-more"
              disabled={
                activeItemsQuery.isFetchingNextPage
              }
              onClick={() =>
                void activeItemsQuery.fetchNextPage()
              }
              type="button"
            >
              {activeItemsQuery.isFetchingNextPage
                ? "Загружаем…"
                : "Показать ещё"}
            </Button>
          ) : null}
        </div>
      ) : (
        <div className="procurement-fields">
          <label>
            Категория
            <Select
              value={category}
              onChange={(event) => {
                setCategory(event.target.value);
                setManufacturerId("");
                setManufacturerSearch("");
                setAttributes({});
              }}
            >
              <option value="">Выберите</option>
              {leaves.map((entry) => (
                <option key={entry.id} value={entry.key}>
                  {entry.display_name}
                </option>
              ))}
            </Select>
          </label>
          {identityRequired ? (
            <>
              <label>
                Поиск производителя
                <Input
                  value={manufacturerSearch}
                  onChange={(event) => {
                    setManufacturerSearch(
                      event.target.value,
                    );
                    setManufacturerId("");
                  }}
                />
              </label>

              <label>
                Производитель
                <Select
                  value={manufacturerId}
                  onChange={(event) =>
                    setManufacturerId(
                      event.target.value,
                    )}
                >
                  <option value="">
                    Выберите
                  </option>
                  {manufacturerOptions.map(
                    (entry) => (
                      <option
                        key={entry.id}
                        value={entry.id}
                      >
                        {entry.name}
                      </option>
                    ),
                  )}
                </Select>
              </label>

              {manufacturers.hasNextPage ? (
                <Button
                  className="button button--load-more"
                  disabled={
                    manufacturers.isFetchingNextPage
                  }
                  onClick={() =>
                    void manufacturers.fetchNextPage()
                  }
                  type="button"
                >
                  {manufacturers.isFetchingNextPage
                    ? "Загружаем производителей…"
                    : "Показать ещё производителей"}
                </Button>
              ) : null}
            </>
          ) : null}
          <label>
            Название
            <Input maxLength={255} value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          {identityRequired ? (
            <label>
              Модель
              <Input maxLength={255} value={model} onChange={(event) => setModel(event.target.value)} />
            </label>
          ) : null}
          {(schema.data?.attributes ?? [])
            .filter((definition) => definition.key !== "reach_m")
            .map((definition) => (
              <AttributeControl
                attribute={definition}
                error={undefined}
                key={definition.id}
                onChange={(value) => {
                  const next = { ...attributes };
                  if (value === undefined) delete next[definition.key];
                  else next[definition.key] = value;
                  setAttributes(next);
                }}
                value={attributes[definition.key]}
              />
            ))}
        </div>
      )}

      <div className="procurement-add-row">
        <label>
          Количество
          <Input inputMode="numeric" value={qty} onChange={(event) => setQty(event.target.value)} />
        </label>
        <Button
          className="button button--accent"
          disabled={lines.length >= MAX_PROCUREMENT_LINES}
          onClick={add}
          type="button"
        >
          Добавить позицию
        </Button>
      </div>
      {lines.length >= MAX_PROCUREMENT_LINES ? (
        <p role="alert">В одной заявке может быть не более 500 позиций.</p>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
