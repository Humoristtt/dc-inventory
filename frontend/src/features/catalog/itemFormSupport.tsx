import {
  useEffect,
  useState,
} from "react";
import {
  useQuery,
} from "@tanstack/react-query";

import {
  AttributeControl,
} from "./AttributeControl";
import {
  draftAttributesFromItem,
  type AttributeDraft,
} from "./itemForm";
import {
  getCatalogFacetPage,
  type CatalogItem,
} from "../../shared/api/catalog";
import type {
  SuggestionOption,
} from "./SuggestionInput";

export type ItemFormDraft = {
  category: string;
  manufacturer: string;
  model: string;
  name: string;
  attributes: AttributeDraft;
};

export const EMPTY_ITEM_FORM_DRAFT:
  ItemFormDraft = {
    category: "",
    manufacturer: "",
    model: "",
    name: "",
    attributes: {},
  };

export function itemDraft(
  item: CatalogItem,
): ItemFormDraft {
  return {
    category: item.category.key,
    manufacturer:
      item.manufacturer?.id ?? "",
    model: item.model ?? "",
    name: item.name,
    attributes:
      draftAttributesFromItem(item),
  };
}

export function useDebouncedValue(
  value: string,
  delay = 180,
): string {
  const [
    debounced,
    setDebounced,
  ] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(
      () => setDebounced(value),
      delay,
    );

    return () =>
      window.clearTimeout(timer);
  }, [delay, value]);

  return debounced;
}

type SmartAttributeControlProps = {
  attribute:
    Parameters<
      typeof AttributeControl
    >[0]["attribute"];
  category: string;
  error: string | undefined;
  onChange: (
    value:
      | string
      | boolean
      | undefined,
  ) => void;
  value:
    | string
    | boolean
    | undefined;
};

export function SmartAttributeControl({
  attribute,
  category,
  error,
  onChange,
  value,
}: SmartAttributeControlProps) {
  const rawValue =
    typeof value === "string"
      ? value
      : "";

  const debouncedValue =
    useDebouncedValue(
      rawValue.trim(),
    );

  const suggestible =
    attribute.data_type === "TEXT"
    && attribute.filterable
    && attribute.filter_type === "EXACT"
    && attribute.searchable;

  const suggestionsQuery = useQuery({
    queryKey: [
      "catalog",
      "form-attribute-suggestions",
      category,
      attribute.key,
      debouncedValue,
    ],
    queryFn: async ({ signal }) => {
      const page =
        await getCatalogFacetPage(
          {
            category,
            q: debouncedValue,
          },
          {
            facet: attribute.key,
            limit: 50,
            offset: 0,
          },
          signal,
        );

      const facet =
        page.facets.find(
          (candidate) =>
            candidate.key
            === attribute.key,
        );

      return (
        facet?.values.map(
          (entry) =>
            String(entry.value),
        )
        ?? []
      );
    },
    enabled:
      suggestible
      && category !== ""
      && debouncedValue.length >= 1,
  });

  return (
    <AttributeControl
      attribute={attribute}
      error={error}
      onChange={onChange}
      suggestions={
        suggestionsQuery.data
        ?? []
      }
      suggestionsLoading={
        suggestionsQuery.isFetching
      }
      value={value}
    />
  );
}

export function textSuggestions(
  values: Array<string | null>,
  query: string,
): SuggestionOption[] {
  const needle =
    query
      .trim()
      .toLocaleLowerCase(
        "ru-RU",
      );

  if (!needle) {
    return [];
  }

  const unique = [
    ...new Set(
      values.filter(
        (
          value,
        ): value is string =>
          Boolean(
            value?.trim(),
          ),
      ),
    ),
  ];

  return unique
    .filter((value) =>
      value
        .toLocaleLowerCase(
          "ru-RU",
        )
        .includes(needle),
    )
    .sort(
      (left, right) => {
        const normalizedLeft =
          left.toLocaleLowerCase(
            "ru-RU",
          );
        const normalizedRight =
          right.toLocaleLowerCase(
            "ru-RU",
          );

        const leftPrefix =
          normalizedLeft
            .startsWith(needle)
            ? 0
            : 1;
        const rightPrefix =
          normalizedRight
            .startsWith(needle)
            ? 0
            : 1;

        if (
          leftPrefix
          !== rightPrefix
        ) {
          return (
            leftPrefix
            - rightPrefix
          );
        }

        return left.localeCompare(
          right,
          "ru",
        );
      },
    )
    .slice(0, 8)
    .map((value) => ({
      key: value,
      label: value,
    }));
}
