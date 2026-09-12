import { useQuery } from "@tanstack/react-query";
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
import type { ProcurementLineInput } from "../../shared/api/procurement";

const manufactured = new Set([
  "transceiver_ethernet",
  "transceiver_fc",
  "network_ethernet",
  "network_fc",
  "ssd",
  "hdd",
  "ram",
  "pcie_adapter",
]);

function quantity(value: string): number | null {
  if (!/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function lineLabel(line: ProcurementLineInput): string {
  if (line.line_type === "EXISTING_ITEM") return `Карточка ${line.item_id}`;
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
  const [existingItemId, setExistingItemId] = useState("");
  const [qty, setQty] = useState("1");
  const [category, setCategory] = useState("");
  const [manufacturerId, setManufacturerId] = useState("");
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
  const schema = useQuery({
    queryKey: ["catalog", "category", category],
    queryFn: ({ signal }) => getCatalogCategory(category, signal),
    enabled: Boolean(category),
    staleTime: 5 * 60_000,
  });
  const manufacturers = useQuery({
    queryKey: ["catalog", "manufacturers", "procurement"],
    queryFn: ({ signal }) =>
      getCatalogManufacturers({ limit: 200, offset: 0 }, signal),
    staleTime: 5 * 60_000,
  });
  const items = useQuery({
    queryKey: ["catalog", "procurement-search", search],
    queryFn: ({ signal }) =>
      getCatalogItems({ q: search, limit: 20, offset: 0 }, signal),
    enabled: search.trim().length >= 2,
  });

  const add = () => {
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
      onChange([
        ...lines,
        { line_type: "EXISTING_ITEM", item_id: existingItemId, quantity: amount },
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
    if (manufactured.has(category) && (!manufacturerId || !model.trim())) {
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
              <button
                className="button button--ghost"
                onClick={() => onChange(lines.filter((_, row) => row !== index))}
                type="button"
              >
                Удалить
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <p className="empty-state">Добавьте хотя бы одну позицию.</p>
      )}

      <div className="procurement-mode" role="group" aria-label="Тип позиции">
        <button
          className={mode === "EXISTING_ITEM" ? "button button--dark" : "button"}
          onClick={() => setMode("EXISTING_ITEM")}
          type="button"
        >
          Из каталога
        </button>
        <button
          className={mode === "PROPOSED_ITEM" ? "button button--dark" : "button"}
          onClick={() => setMode("PROPOSED_ITEM")}
          type="button"
        >
          Новая позиция
        </button>
      </div>

      {mode === "EXISTING_ITEM" ? (
        <div className="procurement-fields">
          <label>
            Поиск по каталогу
            <input value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
          <label>
            Позиция
            <select
              value={existingItemId}
              onChange={(event) => setExistingItemId(event.target.value)}
            >
              <option value="">Выберите</option>
              {(items.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {[item.manufacturer?.name, item.name, item.model]
                    .filter(Boolean)
                    .join(" · ")}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : (
        <div className="procurement-fields">
          <label>
            Категория
            <select
              value={category}
              onChange={(event) => {
                setCategory(event.target.value);
                setAttributes({});
              }}
            >
              <option value="">Выберите</option>
              {leaves.map((entry) => (
                <option key={entry.id} value={entry.key}>
                  {entry.display_name}
                </option>
              ))}
            </select>
          </label>
          {manufactured.has(category) ? (
            <label>
              Производитель
              <select
                value={manufacturerId}
                onChange={(event) => setManufacturerId(event.target.value)}
              >
                <option value="">Выберите</option>
                {(manufacturers.data?.items ?? []).map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label>
            Название
            <input maxLength={255} value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          {manufactured.has(category) ? (
            <label>
              Модель
              <input maxLength={255} value={model} onChange={(event) => setModel(event.target.value)} />
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
          <input inputMode="numeric" value={qty} onChange={(event) => setQty(event.target.value)} />
        </label>
        <button className="button button--accent" onClick={add} type="button">
          Добавить позицию
        </button>
      </div>
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
