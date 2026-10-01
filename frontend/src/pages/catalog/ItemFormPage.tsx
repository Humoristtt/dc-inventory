import { Button } from "../../shared/ui";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  useEffect,
  useRef,
  useState,
} from "react";
import {
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

import { useAuthState } from "../../features/auth/useAuthState";
import { hasCapability } from "../../shared/api/auth";
import {
  type SuggestionOption,
} from "../../features/catalog/SuggestionInput";
import {
  ItemFormAttributeFields,
  ItemFormBasicFields,
} from "../../features/catalog/ItemFormSections";
import {
  validateDraftAttributes,
} from "../../features/catalog/itemForm";
import {
  EMPTY_ITEM_FORM_DRAFT,
  itemDraft,
  textSuggestions,
  useDebouncedValue,
  type ItemFormDraft,
} from "../../features/catalog/itemFormSupport";
import { useInternalBackNavigation } from "../../features/navigation/useTelegramNavigation";
import { ApiRequestError } from "../../shared/api/auth";
import { PageHeader } from "../../shared/ui";
import {
  createAndBindProcurementLine,
  getProcurementRequest,
} from "../../shared/api/procurement";
import {
  createCatalogItem,
  createCatalogManufacturer,
  getCatalogCategories,
  getCatalogCategory,
  getCatalogItem,
  getCatalogItems,
  getCatalogManufacturers,
  patchCatalogItem,
  type ItemWritePayload,
} from "../../shared/api/catalog";
import { useTelegramWebApp } from "../../shared/telegram/useTelegramWebApp";

import "../../features/catalog/admin-catalog.css";
import "../../features/inventory/inventory.css";

export function ItemFormPage() {
  const webApp = useTelegramWebApp();
  const { itemId } = useParams();
  const [params] = useSearchParams();
  const auth = useAuthState();
  const navigate = useNavigate();
  const back = useInternalBackNavigation();
  const client = useQueryClient();

  const [state, setState] = useState<ItemFormDraft | null>(null);
  const [family, setFamily] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [manufacturerName, setManufacturerName] = useState("");
  const [manufacturerInput, setManufacturerInput] = useState("");
  const manufacturerInitialized = useRef(false);
  const procurementIntentRef = useRef<{
    fingerprint: string;
    clientRequestId: string;
  } | null>(null);
  const mutationInFlightRef = useRef(false);

  const item = useQuery({
    queryKey: ["catalog", "item", itemId],
    queryFn: ({ signal }) => getCatalogItem(itemId ?? "", signal),
    enabled: Boolean(itemId),
  });

  const procurementRequestId = params.get("procurementRequestId");
  const procurementLineId = params.get("procurementLineId");
  const procurement = useQuery({
    queryKey: ["procurement", "request", procurementRequestId],
    queryFn: ({ signal }) =>
      getProcurementRequest(procurementRequestId ?? "", signal),
    enabled: Boolean(procurementRequestId && procurementLineId && !itemId),
  });
  const procurementLine = procurement.data?.current_revision.lines.find(
    (line) => line.id === procurementLineId,
  );
  const procurementSnapshot = procurementLine?.display_snapshot;
  const procurementDraft: ItemFormDraft | null = procurementSnapshot
    ? {
        category: String(procurementSnapshot.category_key ?? ""),
        manufacturer:
          typeof procurementSnapshot.manufacturer_id === "string"
            ? procurementSnapshot.manufacturer_id
            : "",
        model:
          typeof procurementSnapshot.model === "string"
            ? procurementSnapshot.model
            : "",
        name: String(procurementSnapshot.name ?? ""),
        attributes: Object.fromEntries(
          Object.entries(
            (procurementSnapshot.attributes ?? {}) as Record<string, unknown>,
          ).map(([key, value]) => [
            key,
            typeof value === "boolean" ? value : String(value),
          ]),
        ),
      }
    : null;

  const categories = useQuery({
    staleTime: 5 * 60_000,
    queryKey: ["catalog", "categories"],
    queryFn: ({ signal }) => getCatalogCategories(signal),
  });

  const draft = state
    ?? (
      item.data
        ? itemDraft(item.data)
        : procurementDraft
          ? procurementDraft
        : {
            ...EMPTY_ITEM_FORM_DRAFT,
            category: params.get("category") ?? "",
          }
    );

  const selected = categories.data?.find(
    (category) => category.key === draft.category,
  );

  const familyId = family || selected?.parent_id || "";

  const leaves = categories.data?.filter(
    (category) => category.parent_id === familyId,
  ) ?? [];

  const identityRequired =
    selected?.requires_manufacturer_model === true;

  const schema = useQuery({
    staleTime: 5 * 60_000,
    queryKey: ["catalog", "category", draft.category],
    queryFn: ({ signal }) =>
      getCatalogCategory(draft.category, signal),
    enabled: Boolean(draft.category),
  });

  const definitions = schema.data?.attributes.filter(
    (attribute) => attribute.key !== "reach_m",
  ) ?? [];

  useEffect(() => {
    if (
      manufacturerInitialized.current
      || (!item.data && !procurementSnapshot)
    ) {
      return;
    }

    manufacturerInitialized.current = true;
    setManufacturerInput(
      item.data?.manufacturer?.name
        ?? (typeof procurementSnapshot?.manufacturer_name === "string"
          ? procurementSnapshot.manufacturer_name
          : ""),
    );
  }, [item.data, procurementSnapshot]);

  const debouncedManufacturer = useDebouncedValue(
    manufacturerInput.trim(),
  );

  const manufacturers = useQuery({
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
      && debouncedManufacturer.length >= 1,
  });

  const debouncedModel = useDebouncedValue(draft.model.trim());

  const modelMatches = useQuery({
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
          category: draft.category,
          manufacturerIds: draft.manufacturer
            ? [draft.manufacturer]
            : undefined,
          limit: 8,
          offset: 0,
        },
        signal,
      ),
    enabled:
      identityRequired
      && Boolean(draft.category)
      && debouncedModel.length >= 2,
  });

  const debouncedName = useDebouncedValue(draft.name.trim());

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
          category: draft.category || undefined,
          manufacturerIds: draft.manufacturer
            ? [draft.manufacturer]
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

  const manufacturerOptions: SuggestionOption[] = (
    manufacturers.data?.items ?? []
  ).map((manufacturer) => ({
    key: manufacturer.id,
    label: manufacturer.name,
  }));

  const modelOptions = textSuggestions(
    modelMatches.data?.items.map((entry) => entry.model) ?? [],
    debouncedModel,
  );

  const nameOptions = textSuggestions(
    nameMatches.data?.items.map((entry) => entry.name) ?? [],
    debouncedName,
  );

  const makerMutation = useMutation({
    mutationFn: () =>
      createCatalogManufacturer(manufacturerName),
    onSuccess: (maker) => {
      setState({
        ...draft,
        manufacturer: maker.id,
      });
      setManufacturerInput(maker.name);
      setManufacturerName("");

      void client.invalidateQueries({
        queryKey: ["catalog", "manufacturer-suggestions"],
      });
    },
  });

  const mutation = useMutation({
    mutationFn: async (payload: ItemWritePayload) => {
      if (itemId) {
        const {
          category_key: _categoryKey,
          ...patch
        } = payload;

        return {
          kind: "item" as const,
          saved: await patchCatalogItem(itemId, patch),
        };
      }

      if (procurement.data && procurementLineId && procurementRequestId) {
        const fingerprint = JSON.stringify({
          requestId: procurement.data.id,
          stateVersion: procurement.data.state_version,
          revisionId: procurement.data.current_revision_id,
          lineId: procurementLineId,
          item: payload,
        });
        let intent = procurementIntentRef.current;

        if (
          intent === null
          || intent.fingerprint !== fingerprint
        ) {
          intent = {
            fingerprint,
            clientRequestId: crypto.randomUUID(),
          };
          procurementIntentRef.current = intent;
        }

        return {
          kind: "procurement" as const,
          saved: await createAndBindProcurementLine(
            procurement.data,
            procurementLineId,
            payload,
            intent.clientRequestId,
          ),
        };
      }

      return {
        kind: "item" as const,
        saved: await createCatalogItem(payload),
      };
    },
    onSuccess: ({ kind, saved }) => {
      if (kind === "procurement") {
        procurementIntentRef.current = null;
        client.setQueryData(
          ["procurement", "request", saved.id],
          saved,
        );
        void client.invalidateQueries({ queryKey: ["catalog"] });
        navigate(`/procurement/${saved.id}`, { replace: true });
        return;
      }

      client.setQueryData(
        ["catalog", "item", saved.id],
        saved,
      );

      void client.invalidateQueries({
        queryKey: ["catalog", "items"],
      });

      void client.invalidateQueries({
        queryKey: ["catalog", "facets"],
      });

      void client.invalidateQueries({
        queryKey: ["catalog", "form-model-suggestions"],
      });

      void client.invalidateQueries({
        queryKey: ["catalog", "form-name-suggestions"],
      });

      void client.invalidateQueries({
        queryKey: ["catalog", "form-attribute-suggestions"],
      });

      navigate(`/catalog/items/${saved.id}`, { replace: true });
    },
    onSettled: () => {
      mutationInFlightRef.current = false;
    },
  });

  const update = (next: Partial<ItemFormDraft>) => {
    setState({
      ...draft,
      ...next,
    });
    setErrors({});
    mutation.reset();
  };

  if (
    auth.isPending
    || (itemId && item.isPending)
    || (procurementRequestId && procurement.isPending)
  ) {
    return <p role="status">Загрузка…</p>;
  }

  if (!hasCapability(auth.data?.user, "catalog.manage")) {
    return <Navigate replace to="/catalog" />;
  }

  if (itemId && item.isError) {
    return (
      <p role="alert">
        Не удалось загрузить оборудование.{" "}
        <Button onClick={() => void item.refetch()}>
          Повторить
        </Button>
      </p>
    );
  }

  if (procurementRequestId && (procurement.isError || !procurementLine)) {
    return <p role="alert">Не удалось загрузить позицию закупки.</p>;
  }

  const telegramOwnsBack =
    webApp?.BackButton !== undefined;

  return (
    <main className="catalog-page">
      <PageHeader
        kicker="Каталог"
        onBack={
          !telegramOwnsBack
            ? back
            : undefined
        }
        title={
          itemId
            ? "Редактировать оборудование"
            : "Добавить оборудование"
        }
      />

      <div className="catalog-page__body">
        <form
          autoComplete="off"
          className="catalog-form form-surface"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();

            const validation = validateDraftAttributes(
              definitions,
              draft.attributes,
            );

            const next = {
              ...validation.errors,
            };

            if (!draft.category) {
              next.category = "Выберите категорию";
            }

            if (!draft.name.trim()) {
              next.name = "Укажите название";
            }

            if (
              identityRequired
              && (
                !draft.manufacturer
                || !draft.model.trim()
              )
            ) {
              next.identity =
                "Укажите производителя и модель";
            }

            setErrors(next);

            if (
              Object.keys(next).length
              || !schema.isSuccess
              || mutation.isPending
              || mutationInFlightRef.current
            ) {
              return;
            }

            mutationInFlightRef.current = true;
            mutation.mutate({
              category_key: draft.category,
              manufacturer_id: identityRequired
                ? draft.manufacturer || null
                : null,
              model: identityRequired
                ? draft.model.trim() || null
                : null,
              name: draft.name.trim(),
              attributes: validation.values,
            });
          }}
        >
          <ItemFormBasicFields
            categories={
              categories.data ?? []
            }
            categoriesError={
              categories.isError
            }
            createManufacturerError={
              makerMutation.isError
            }
            creatingManufacturer={
              makerMutation.isPending
            }
            disabled={mutation.isPending}
            draft={draft}
            editing={Boolean(itemId)}
            familyId={familyId}
            identityRequired={
              identityRequired
            }
            leaves={leaves}
            manufacturerInput={
              manufacturerInput
            }
            manufacturerLoading={
              manufacturers.isFetching
            }
            manufacturerName={
              manufacturerName
            }
            manufacturerOptions={
              manufacturerOptions
            }
            manufacturerSuggestionsError={
              manufacturers.isError
            }
            modelLoading={
              modelMatches.isFetching
            }
            modelOptions={modelOptions}
            nameLoading={
              nameMatches.isFetching
            }
            nameOptions={nameOptions}
            onCategoryChange={(value) => {
              setManufacturerInput("");
              update({
                ...EMPTY_ITEM_FORM_DRAFT,
                category: value,
              });
            }}
            onCreateManufacturer={() =>
              makerMutation.mutate()
            }
            onFamilyChange={(value) => {
              setFamily(value);
              setManufacturerInput("");

              const options =
                categories.data?.filter(
                  (category) =>
                    category.parent_id
                    === value,
                ) ?? [];

              update({
                ...EMPTY_ITEM_FORM_DRAFT,
                category:
                  options.length === 1
                    ? options[0].key
                    : "",
              });
            }}
            onManufacturerInputChange={
              (value) => {
                setManufacturerInput(value);

                if (draft.manufacturer) {
                  update({
                    manufacturer: "",
                  });
                }
              }
            }
            onManufacturerNameChange={
              setManufacturerName
            }
            onManufacturerSelect={
              (option) => {
                setManufacturerInput(
                  option.label,
                );
                update({
                  manufacturer:
                    option.key,
                });
              }
            }
            onModelChange={(value) =>
              update({
                model: value,
              })
            }
            onNameChange={(value) =>
              update({
                name: value,
              })
            }
            onRetryCategories={() =>
              void categories.refetch()
            }
            onRetryManufacturers={() =>
              void manufacturers.refetch()
            }
            selected={selected}
          />

          <ItemFormAttributeFields
            category={draft.category}
            definitions={definitions}
            disabled={mutation.isPending}
            errors={errors}
            loading={schema.isPending}
            loadError={schema.isError}
            onChange={(key, value) => {
              const attributes = {
                ...draft.attributes,
              };

              if (value === undefined) {
                delete attributes[key];
              } else {
                attributes[key] = value;
              }

              update({
                attributes,
              });
            }}
            onRetry={() =>
              void schema.refetch()
            }
            values={draft.attributes}
          />

          {Object.keys(errors).length ? (
            <p role="alert">
              {Object.values(errors).join(". ")}
            </p>
          ) : null}

          {mutation.isError ? (
            <p role="alert">
              {mutation.error instanceof ApiRequestError
                && mutation.error.status === 409
                ? "Такая позиция уже существует. Проверьте полную техническую идентичность."
                : mutation.error instanceof ApiRequestError
                    && mutation.error.status === 423
                  ? "Изменения каталога пока отключены администратором."
                  : "Не удалось сохранить. Проверьте обязательные поля и дальность."}
            </p>
          ) : null}

          <Button
            className="button button--dark catalog-form__submit"
            disabled={
              mutation.isPending
              || !schema.isSuccess
            }
            type="submit"
          >
            {mutation.isPending
              ? "Сохраняем…"
              : "Сохранить"}
          </Button>
        </form>
      </div>
    </main>
  );
}
