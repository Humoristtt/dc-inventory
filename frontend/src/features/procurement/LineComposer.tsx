import { Button, Input } from "../../shared/ui";
import { useState } from "react";

import {
  validateDraftAttributes,
  type AttributeDraft,
} from "../catalog/itemForm";
import {
  ExistingItemFields,
  ProposedItemFields,
} from "./LineComposerFields";
import {
  MAX_PROCUREMENT_LINES,
  lineLabel,
  quantity,
} from "./lineComposerModel";
import {
  useLineComposerCatalogData,
} from "./useLineComposerCatalogData";
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

  const {
    activeItemsQuery,
    browseItems,
    categoryGroups,
    identityRequired,
    itemOptions,
    leaves,
    manufacturerOptions,
    manufacturers,
    schema,
    searchItems,
  } = useLineComposerCatalogData({
    catalogCategory,
    category,
    manufacturerSearch,
    mode,
    search,
  });

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
