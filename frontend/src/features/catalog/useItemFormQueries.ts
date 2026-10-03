import {
  useQuery,
} from "@tanstack/react-query";

import {
  getCatalogCategories,
  getCatalogCategory,
  getCatalogItem,
  getCatalogItems,
  getCatalogManufacturers,
} from "../../shared/api/catalog";
import {
  getProcurementRequest,
} from "../../shared/api/procurement";
import type {
  SuggestionOption,
} from "./SuggestionInput";
import {
  textSuggestions,
  useDebouncedValue,
  type ItemFormDraft,
} from "./itemFormSupport";

export function procurementDraftFromSnapshot(
  snapshot:
    | Record<string, unknown>
    | undefined,
): ItemFormDraft | null {
  if (!snapshot) {
    return null;
  }

  return {
    category:
      String(
        snapshot.category_key ?? "",
      ),
    manufacturer:
      typeof snapshot.manufacturer_id
        === "string"
        ? snapshot.manufacturer_id
        : "",
    model:
      typeof snapshot.model
        === "string"
        ? snapshot.model
        : "",
    name:
      String(
        snapshot.name ?? "",
      ),
    attributes:
      Object.fromEntries(
        Object.entries(
          (
            snapshot.attributes ?? {}
          ) as Record<
            string,
            unknown
          >,
        ).map(
          ([key, value]) => [
            key,
            typeof value
              === "boolean"
              ? value
              : String(value),
          ],
        ),
      ),
  };
}

export function useItemFormBaseQueries({
  itemId,
  procurementRequestId,
  procurementLineId,
}: {
  itemId: string | undefined;
  procurementRequestId:
    | string
    | null;
  procurementLineId:
    | string
    | null;
}) {
  const item = useQuery({
    queryKey: [
      "catalog",
      "item",
      itemId,
    ],
    queryFn: ({ signal }) =>
      getCatalogItem(
        itemId ?? "",
        signal,
      ),
    enabled: Boolean(itemId),
  });

  const procurement = useQuery({
    queryKey: [
      "procurement",
      "request",
      procurementRequestId,
    ],
    queryFn: ({ signal }) =>
      getProcurementRequest(
        procurementRequestId ?? "",
        signal,
      ),
    enabled: Boolean(
      procurementRequestId
      && procurementLineId
      && !itemId,
    ),
  });

  const procurementLine =
    procurement.data
      ?.current_revision.lines.find(
        (line) =>
          line.id
          === procurementLineId,
      );

  const procurementSnapshot =
    procurementLine
      ?.display_snapshot;

  const categories = useQuery({
    staleTime: 5 * 60_000,
    queryKey: [
      "catalog",
      "categories",
    ],
    queryFn: ({ signal }) =>
      getCatalogCategories(
        signal,
      ),
  });

  return {
    categories,
    item,
    procurement,
    procurementDraft:
      procurementDraftFromSnapshot(
        procurementSnapshot,
      ),
    procurementLine,
    procurementSnapshot,
  };
}

export function useItemFormSuggestions({
  draft,
  identityRequired,
  manufacturerInput,
}: {
  draft: ItemFormDraft;
  identityRequired: boolean;
  manufacturerInput: string;
}) {
  const schema = useQuery({
    staleTime: 5 * 60_000,
    queryKey: [
      "catalog",
      "category",
      draft.category,
    ],
    queryFn: ({ signal }) =>
      getCatalogCategory(
        draft.category,
        signal,
      ),
    enabled:
      Boolean(draft.category),
  });

  const definitions =
    schema.data?.attributes.filter(
      (attribute) =>
        attribute.key !== "reach_m",
    ) ?? [];

  const debouncedManufacturer =
    useDebouncedValue(
      manufacturerInput.trim(),
    );

  const manufacturers =
    useQuery({
      queryKey: [
        "catalog",
        "manufacturer-suggestions",
        debouncedManufacturer,
      ],
      queryFn: ({ signal }) =>
        getCatalogManufacturers(
          {
            q: debouncedManufacturer,
            limit: 8,
            offset: 0,
          },
          signal,
        ),
      enabled:
        identityRequired
        && debouncedManufacturer
          .length >= 1,
    });

  const debouncedModel =
    useDebouncedValue(
      draft.model.trim(),
    );

  const modelMatches =
    useQuery({
      queryKey: [
        "catalog",
        "form-model-suggestions",
        draft.category,
        draft.manufacturer,
        debouncedModel,
      ],
      queryFn: ({ signal }) =>
        getCatalogItems(
          {
            q: debouncedModel,
            category:
              draft.category,
            manufacturerIds:
              draft.manufacturer
                ? [
                    draft
                      .manufacturer,
                  ]
                : undefined,
            limit: 8,
            offset: 0,
          },
          signal,
        ),
      enabled:
        identityRequired
        && Boolean(
          draft.category,
        )
        && debouncedModel
          .length >= 2,
    });

  const debouncedName =
    useDebouncedValue(
      draft.name.trim(),
    );

  const nameMatches = useQuery({
    queryKey: [
      "catalog",
      "form-name-suggestions",
      draft.category,
      draft.manufacturer,
      debouncedName,
    ],
    queryFn: ({ signal }) =>
      getCatalogItems(
        {
          q: debouncedName,
          category:
            draft.category
            || undefined,
          manufacturerIds:
            draft.manufacturer
              ? [
                  draft
                    .manufacturer,
                ]
              : undefined,
          limit: 8,
          offset: 0,
        },
        signal,
      ),
    enabled:
      Boolean(draft.category)
      && debouncedName.length >= 2,
  });

  const manufacturerOptions:
    SuggestionOption[] = (
      manufacturers.data?.items
      ?? []
    ).map(
      (manufacturer) => ({
        key: manufacturer.id,
        label:
          manufacturer.name,
      }),
    );

  const modelOptions =
    textSuggestions(
      modelMatches.data?.items.map(
        (entry) =>
          entry.model,
      ) ?? [],
      debouncedModel,
    );

  const nameOptions =
    textSuggestions(
      nameMatches.data?.items.map(
        (entry) =>
          entry.name,
      ) ?? [],
      debouncedName,
    );

  return {
    definitions,
    manufacturerOptions,
    manufacturers,
    modelMatches,
    modelOptions,
    nameMatches,
    nameOptions,
    schema,
  };
}
