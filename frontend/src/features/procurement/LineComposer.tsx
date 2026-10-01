import { Button, Input } from "../../shared/ui";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

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
import {
  ExistingItemFields,
  ProposedItemFields,
} from "./LineComposerFields";
import {
  MAX_PROCUREMENT_LINES,
  lineLabel,
  quantity,
} from "./lineComposerModel";
import type { ProcurementLineInput } from "../../shared/api/procurement";

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
        <ExistingItemFields
          catalogCategory={
            catalogCategory
          }
          categoryGroups={
            categoryGroups
          }
          existingItemId={
            existingItemId
          }
          hasNextPage={
            activeItemsQuery.hasNextPage
            ?? false
          }
          itemOptions={itemOptions}
          loading={
            browseItems.isPending
          }
          loadingNext={
            activeItemsQuery
              .isFetchingNextPage
          }
          onCatalogCategoryChange={
            (value) => {
              setCatalogCategory(value);
              setExistingItemId("");
            }
          }
          onExistingItemChange={
            setExistingItemId
          }
          onLoadMore={() =>
            void activeItemsQuery
              .fetchNextPage()
          }
          onSearchChange={(value) => {
            setSearch(value);
            setExistingItemId("");
          }}
          search={search}
          searchEmpty={
            search.trim().length >= 2
            && !searchItems.isFetching
            && itemOptions.length === 0
          }
        />
      ) : (
        <ProposedItemFields
          attributes={attributes}
          category={category}
          definitions={
            schema.data?.attributes
              .filter(
                (definition) =>
                  definition.key
                  !== "reach_m",
              ) ?? []
          }
          identityRequired={
            identityRequired
          }
          leaves={leaves}
          manufacturerId={
            manufacturerId
          }
          manufacturerOptions={
            manufacturerOptions
          }
          manufacturerSearch={
            manufacturerSearch
          }
          manufacturersHaveNextPage={
            manufacturers.hasNextPage
            ?? false
          }
          manufacturersLoadingNext={
            manufacturers
              .isFetchingNextPage
          }
          model={model}
          name={name}
          onAttributeChange={
            (key, value) => {
              const next = {
                ...attributes,
              };

              if (
                value === undefined
              ) {
                delete next[key];
              } else {
                next[key] = value;
              }

              setAttributes(next);
            }
          }
          onCategoryChange={(value) => {
            setCategory(value);
            setManufacturerId("");
            setManufacturerSearch("");
            setAttributes({});
          }}
          onLoadMoreManufacturers={
            () =>
              void manufacturers
                .fetchNextPage()
          }
          onManufacturerChange={
            setManufacturerId
          }
          onManufacturerSearchChange={
            (value) => {
              setManufacturerSearch(
                value,
              );
              setManufacturerId("");
            }
          }
          onModelChange={setModel}
          onNameChange={setName}
        />
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
