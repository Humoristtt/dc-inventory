import { useEffect, useMemo, useState } from "react";

import type {
  CatalogAttributeFilter,
  CatalogFacet,
  CategoryAttribute,
  FacetValue,
} from "../../shared/api/catalog";
import {
  defaultCatalogFilterState,
  type CatalogFilterState,
} from "./catalogQuery";

type FilterSheetProps = {
  active: CatalogFilterState;
  facets: CatalogFacet[];
  attributes: CategoryAttribute[];
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  onLoadMore?: (
    facetKey: string,
    offset: number,
  ) => Promise<CatalogFacet>;
  onApply: (next: CatalogFilterState) => void;
  onCancel: () => void;
};

const commonFacetOrder = new Map([
  ["manufacturer", 0],
  ["availability", 1],
  ["location", 2],
]);

function cloneState(state: CatalogFilterState): CatalogFilterState {
  return {
    ...state,
    manufacturerIds: [...state.manufacturerIds],
    locationIds: [...state.locationIds],
    filters: state.filters.map((filter) => ({ ...filter })),
  };
}

function stringValue(value: FacetValue["value"]): string {
  return typeof value === "boolean" ? String(value).toLowerCase() : String(value);
}

function facetValueLabel(facet: CatalogFacet, value: FacetValue): string {
  if (facet.data_type === "BOOLEAN") {
    return value.value === true || value.value === "true" ? "Да" : "Нет";
  }
  return value.label ?? value.name ?? value.code ?? String(value.value);
}

function exactValues(state: CatalogFilterState, key: string): string[] {
  if (key === "manufacturer") {
    return state.manufacturerIds;
  }
  if (key === "location") {
    return state.locationIds;
  }
  if (key === "availability") {
    return state.availability === "ANY" ? [] : [state.availability];
  }
  return state.filters
    .filter((filter) => filter.key === key && filter.operator === "eq")
    .map((filter) => filter.value);
}

function updateExactValue(
  state: CatalogFilterState,
  key: string,
  value: string,
  selected: boolean,
): CatalogFilterState {
  if (key === "manufacturer") {
    return {
      ...state,
      manufacturerIds: selected
        ? [...new Set([...state.manufacturerIds, value])]
        : state.manufacturerIds.filter((current) => current !== value),
    };
  }
  if (key === "location") {
    return {
      ...state,
      locationIds: selected
        ? [...new Set([...state.locationIds, value])]
        : state.locationIds.filter((current) => current !== value),
    };
  }
  if (key === "availability") {
    return {
      ...state,
      availability: selected && (value === "IN_STOCK" || value === "OUT_OF_STOCK")
        ? value
        : "ANY",
    };
  }

  const remaining = state.filters.filter(
    (filter) =>
      !(filter.key === key && filter.operator === "eq" && filter.value === value),
  );
  return {
    ...state,
    filters: selected
      ? [...remaining, { key, operator: "eq", value }]
      : remaining,
  };
}

function updateRange(
  state: CatalogFilterState,
  key: string,
  operator: "gte" | "lte",
  value: string,
): CatalogFilterState {
  const remaining = state.filters.filter(
    (filter) => !(filter.key === key && filter.operator === operator),
  );
  return {
    ...state,
    filters: value === ""
      ? remaining
      : [...remaining, { key, operator, value }],
  };
}

function rangeValue(
  filters: CatalogAttributeFilter[],
  key: string,
  operator: "gte" | "lte",
): string {
  return filters.find(
    (filter) => filter.key === key && filter.operator === operator,
  )?.value ?? "";
}

function facetHasVisibleControls(
  facet: CatalogFacet,
  state: CatalogFilterState,
): boolean {
  if (facet.filter_type === "RANGE") {
    return (
      facet.min !== null
      || facet.max !== null
      || rangeValue(state.filters, facet.key, "gte") !== ""
      || rangeValue(state.filters, facet.key, "lte") !== ""
    );
  }

  return facet.values.length > 0 || exactValues(state, facet.key).length > 0;
}

export function FilterSheet({
  active,
  facets,
  attributes,
  loading = false,
  error = false,
  onRetry,
  onLoadMore,
  onApply,
  onCancel,
}: FilterSheetProps) {
  const [draft, setDraft] = useState(() => cloneState(active));
  const [loadedFacetPages, setLoadedFacetPages] = useState<
    Record<string, {
      values: FacetValue[];
      hasMore: boolean;
    }>
  >({});
  const [loadingFacetKey, setLoadingFacetKey] = useState<string | null>(
    null,
  );
  const [facetLoadErrors, setFacetLoadErrors] = useState<
    Record<string, boolean>
  >({});

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  const orderedFacets = useMemo(() => {
    const attributeOrder = new Map(
      attributes.map((attribute) => [attribute.key, attribute.sort_order]),
    );
    return [...facets].sort((left, right) => {
      const leftOrder = commonFacetOrder.get(left.key)
        ?? 100 + (attributeOrder.get(left.key) ?? 10_000);
      const rightOrder = commonFacetOrder.get(right.key)
        ?? 100 + (attributeOrder.get(right.key) ?? 10_000);
      return leftOrder - rightOrder;
    });
  }, [attributes, facets]);

  const visibleFacets = useMemo(
    () => orderedFacets.filter((facet) => facetHasVisibleControls(facet, draft)),
    [draft, orderedFacets],
  );

  const loadMoreFacet = async (facet: CatalogFacet) => {
    if (onLoadMore === undefined || loadingFacetKey === facet.key) {
      return;
    }

    const loaded = loadedFacetPages[facet.key];
    const offset = facet.values.length + (loaded?.values.length ?? 0);

    setLoadingFacetKey(facet.key);
    setFacetLoadErrors((current) => ({
      ...current,
      [facet.key]: false,
    }));

    try {
      const nextFacet = await onLoadMore(facet.key, offset);

      if (nextFacet.key !== facet.key) {
        throw new Error(`Facet page mismatch for ${facet.key}`);
      }

      setLoadedFacetPages((current) => {
        const existing = current[facet.key]?.values ?? [];
        const known = new Set(
          [...facet.values, ...existing].map((value) =>
            stringValue(value.value)
          ),
        );
        const additions = nextFacet.values.filter(
          (value) => !known.has(stringValue(value.value)),
        );

        return {
          ...current,
          [facet.key]: {
            values: [...existing, ...additions],
            hasMore:
              nextFacet.values_has_more
              && nextFacet.values.length > 0,
          },
        };
      });
    } catch {
      setFacetLoadErrors((current) => ({
        ...current,
        [facet.key]: true,
      }));
    } finally {
      setLoadingFacetKey((current) =>
        current === facet.key ? null : current
      );
    }
  };

  return (
    <div
      className="sheet-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onCancel();
        }
      }}
    >
      <section
        aria-labelledby="filter-sheet-title"
        aria-modal="true"
        className="sheet filter-sheet"
        role="dialog"
      >
        <header className="sheet__header">
          <div>
            <span className="section-kicker">Отбор оборудования</span>
            <h2 id="filter-sheet-title">Фильтры</h2>
          </div>
          <button
            aria-label="Закрыть фильтры"
            className="icon-button"
            onClick={onCancel}
            type="button"
          >
            ×
          </button>
        </header>

        <div className="sheet__body">
          {loading ? (
            <div className="filter-loading" aria-label="Загрузка фильтров">
              <span />
              <span />
              <span />
            </div>
          ) : null}
          {error ? (
            <div className="filter-inline-error" role="alert">
              <p>Не удалось загрузить варианты фильтров.</p>
              {onRetry ? (
                <button className="text-button" onClick={onRetry} type="button">
                  Повторить
                </button>
              ) : null}
            </div>
          ) : null}
          {!loading && !error && visibleFacets.length === 0 ? (
            <p className="filter-empty">Для этой выборки фильтры недоступны.</p>
          ) : null}

          {!loading && !error ? visibleFacets.map((facet) => {
            const metadata = attributes.find((attribute) => attribute.key === facet.key);
            const label = metadata?.label ?? facet.label;
            const unit = metadata?.unit ?? facet.unit;
            const selectedValues = exactValues(draft, facet.key);

            if (facet.filter_type === "RANGE") {
              return (
                <fieldset className="filter-group" key={facet.key}>
                  <legend>
                    {label}
                    {unit ? <span> · {unit}</span> : null}
                  </legend>
                  <div className="range-filter">
                    <label>
                      <span>От</span>
                      <input
                        aria-label={`${label}: от`}
                        inputMode="decimal"
                        max={facet.max ?? undefined}
                        min={facet.min ?? undefined}
                        onChange={(event) =>
                          setDraft((current) =>
                            updateRange(current, facet.key, "gte", event.target.value),
                          )
                        }
                        placeholder={facet.min === null ? "—" : String(facet.min)}
                        step={facet.data_type === "INTEGER" ? 1 : "any"}
                        type="number"
                        value={rangeValue(draft.filters, facet.key, "gte")}
                      />
                    </label>
                    <span aria-hidden="true">—</span>
                    <label>
                      <span>До</span>
                      <input
                        aria-label={`${label}: до`}
                        inputMode="decimal"
                        max={facet.max ?? undefined}
                        min={facet.min ?? undefined}
                        onChange={(event) =>
                          setDraft((current) =>
                            updateRange(current, facet.key, "lte", event.target.value),
                          )
                        }
                        placeholder={facet.max === null ? "—" : String(facet.max)}
                        step={facet.data_type === "INTEGER" ? 1 : "any"}
                        type="number"
                        value={rangeValue(draft.filters, facet.key, "lte")}
                      />
                    </label>
                  </div>
                </fieldset>
              );
            }

            const loadedFacet = loadedFacetPages[facet.key];
            const backendValues = [
              ...facet.values,
              ...(loadedFacet?.values ?? []),
            ];
            const hasMore = loadedFacet?.hasMore ?? facet.values_has_more;
            const knownValues = new Set(
              backendValues.map((value) => stringValue(value.value)),
            );
            const values = [
              ...backendValues,
              ...selectedValues
                .filter((value) => !knownValues.has(value))
                .map((value) => ({
                  value,
                  count: 0,
                  label: value,
                  code: null,
                  name: null,
                })),
            ];

            return (
              <fieldset className="filter-group" key={facet.key}>
                <legend>{label}</legend>
                <div className="filter-options">
                  {values.map((value) => {
                    const machineValue = stringValue(value.value);
                    const checked = selectedValues.includes(machineValue);
                    const disabled = value.count === 0 && !checked;
                    return (
                      <label
                        className={disabled ? "filter-option filter-option--disabled" : "filter-option"}
                        key={machineValue}
                      >
                        <input
                          aria-label={facetValueLabel(facet, value)}
                          checked={checked}
                          disabled={disabled}
                          name={`${facet.key}:${machineValue}`}
                          onChange={(event) =>
                            setDraft((current) =>
                              updateExactValue(
                                current,
                                facet.key,
                                machineValue,
                                event.target.checked,
                              ),
                            )
                          }
                          type="checkbox"
                        />
                        <span className="filter-option__check" aria-hidden="true" />
                        <span className="filter-option__label">
                          {facetValueLabel(facet, value)}
                        </span>
                        <span className="filter-option__count">{value.count}</span>
                      </label>
                    );
                  })}
                </div>
                {hasMore && onLoadMore !== undefined ? (
                  <button
                    aria-label={`Показать ещё: ${label}`}
                    className="text-button"
                    disabled={loadingFacetKey === facet.key}
                    onClick={() => void loadMoreFacet(facet)}
                    type="button"
                  >
                    {loadingFacetKey === facet.key
                      ? "Загружаем…"
                      : facetLoadErrors[facet.key]
                        ? "Повторить загрузку"
                        : "Показать ещё"}
                  </button>
                ) : null}
                {facetLoadErrors[facet.key] ? (
                  <p className="filter-inline-error" role="alert">
                    Не удалось загрузить дополнительные варианты.
                  </p>
                ) : null}
              </fieldset>
            );
          }) : null}
        </div>

        <footer className="sheet__footer">
          <button
            className="button button--ghost"
            onClick={() => setDraft(cloneState(defaultCatalogFilterState))}
            type="button"
          >
            Сбросить
          </button>
          <button
            className="button button--accent"
            disabled={loading || error}
            onClick={() => onApply(cloneState(draft))}
            type="button"
          >
            Применить
          </button>
        </footer>
      </section>
    </div>
  );
}
