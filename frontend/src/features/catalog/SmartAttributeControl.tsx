import {
  useQuery,
} from "@tanstack/react-query";

import {
  AttributeControl,
} from "./AttributeControl";
import {
  useDebouncedValue,
} from "./itemFormSupport";
import {
  getCatalogFacetPage,
} from "../../shared/api/catalog";

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
