import {
  useEffect,
  useState,
} from "react";

import {
  draftAttributesFromItem,
  type AttributeDraft,
} from "./itemForm";
import type {
  CatalogItem,
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
