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
import { AttributeControl } from "../../features/catalog/AttributeControl";
import {
  SuggestionInput,
  type SuggestionOption,
} from "../../features/catalog/SuggestionInput";
import {
  draftAttributesFromItem,
  validateDraftAttributes,
  type AttributeDraft,
} from "../../features/catalog/itemForm";
import { useInternalBackNavigation } from "../../features/navigation/useTelegramNavigation";
import { ApiRequestError } from "../../shared/api/auth";
import {
  createCatalogItem,
  createCatalogManufacturer,
  getCatalogCategories,
  getCatalogCategory,
  getCatalogFacetPage,
  getCatalogItem,
  getCatalogItems,
  getCatalogManufacturers,
  patchCatalogItem,
  type CatalogItem,
  type ItemWritePayload,
} from "../../shared/api/catalog";
import { SpikatelBrand } from "../../shared/brand/SpikatelBrand";
import { TelegramFullscreenButton } from "../../shared/telegram/TelegramFullscreenButton";
import { useTelegramWebApp } from "../../shared/telegram/useTelegramWebApp";

import "../../features/catalog/admin-catalog.css";
import "../../features/inventory/inventory.css";

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

type Draft = {
  category: string;
  manufacturer: string;
  model: string;
  name: string;
  attributes: AttributeDraft;
};

const empty: Draft = {
  category: "",
  manufacturer: "",
  model: "",
  name: "",
  attributes: {},
};

function itemDraft(item: CatalogItem): Draft {
  return {
    category: item.category.key,
    manufacturer: item.manufacturer?.id ?? "",
    model: item.model ?? "",
    name: item.name,
    attributes: draftAttributesFromItem(item),
  };
}

function useDebouncedValue(value: string, delay = 180) {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(
      () => setDebounced(value),
      delay,
    );

    return () => window.clearTimeout(timer);
  }, [delay, value]);

  return debounced;
}

type SmartAttributeControlProps = {
  attribute: Parameters<typeof AttributeControl>[0]["attribute"];
  category: string;
  error: string | undefined;
  onChange: (value: string | boolean | undefined) => void;
  value: string | boolean | undefined;
};

function SmartAttributeControl({
  attribute,
  category,
  error,
  onChange,
  value,
}: SmartAttributeControlProps) {
  const rawValue = typeof value === "string" ? value : "";

  const debouncedValue = useDebouncedValue(
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
      const page = await getCatalogFacetPage(
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

      const facet = page.facets.find(
        (candidate) =>
          candidate.key === attribute.key,
      );

      return facet?.values.map(
        (entry) => String(entry.value),
      ) ?? [];
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
      suggestions={suggestionsQuery.data ?? []}
      suggestionsLoading={suggestionsQuery.isFetching}
      value={value}
    />
  );
}

function textSuggestions(
  values: Array<string | null>,
  query: string,
): SuggestionOption[] {
  const needle = query.trim().toLocaleLowerCase("ru-RU");

  if (!needle) {
    return [];
  }

  const unique = [
    ...new Set(
      values.filter(
        (value): value is string => Boolean(value?.trim()),
      ),
    ),
  ];

  return unique
    .filter((value) =>
      value.toLocaleLowerCase("ru-RU").includes(needle),
    )
    .sort((left, right) => {
      const normalizedLeft = left.toLocaleLowerCase("ru-RU");
      const normalizedRight = right.toLocaleLowerCase("ru-RU");

      const leftPrefix = normalizedLeft.startsWith(needle) ? 0 : 1;
      const rightPrefix = normalizedRight.startsWith(needle) ? 0 : 1;

      if (leftPrefix !== rightPrefix) {
        return leftPrefix - rightPrefix;
      }

      return left.localeCompare(right, "ru");
    })
    .slice(0, 8)
    .map((value) => ({
      key: value,
      label: value,
    }));
}

export function ItemFormPage() {
  const webApp = useTelegramWebApp();
  const { itemId } = useParams();
  const [params] = useSearchParams();
  const auth = useAuthState();
  const navigate = useNavigate();
  const back = useInternalBackNavigation();
  const client = useQueryClient();

  const [state, setState] = useState<Draft | null>(null);
  const [family, setFamily] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [manufacturerName, setManufacturerName] = useState("");
  const [manufacturerInput, setManufacturerInput] = useState("");

  const manufacturerInitialized = useRef(false);

  const item = useQuery({
    queryKey: ["catalog", "item", itemId],
    queryFn: ({ signal }) => getCatalogItem(itemId ?? "", signal),
    enabled: Boolean(itemId),
  });

  const categories = useQuery({
    staleTime: 5 * 60_000,
    queryKey: ["catalog", "categories"],
    queryFn: ({ signal }) => getCatalogCategories(signal),
  });

  const draft = state
    ?? (
      item.data
        ? itemDraft(item.data)
        : {
            ...empty,
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

  const identityRequired = manufactured.has(draft.category);

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
      || !item.data
    ) {
      return;
    }

    manufacturerInitialized.current = true;
    setManufacturerInput(item.data.manufacturer?.name ?? "");
  }, [item.data]);

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
    mutationFn: (payload: ItemWritePayload) => {
      if (itemId) {
        const {
          category_key: _categoryKey,
          ...patch
        } = payload;

        return patchCatalogItem(itemId, patch);
      }

      return createCatalogItem(payload);
    },
    onSuccess: (saved) => {
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

      navigate(
        `/catalog/items/${saved.id}`,
        { replace: true },
      );
    },
  });

  const update = (next: Partial<Draft>) => {
    setState({
      ...draft,
      ...next,
    });
    setErrors({});
    mutation.reset();
  };

  if (auth.isPending || (itemId && item.isPending)) {
    return <p role="status">Загрузка…</p>;
  }

  if (auth.data?.user.role !== "ADMIN") {
    return <Navigate replace to="/catalog" />;
  }

  if (itemId && item.isError) {
    return (
      <p role="alert">
        Не удалось загрузить оборудование.{" "}
        <button onClick={() => void item.refetch()}>
          Повторить
        </button>
      </p>
    );
  }

  const telegramOwnsBack =
    webApp?.BackButton !== undefined;

  return (
    <main className="catalog-page">
      <header className="detail-header">
        <div className="page-toolbar page-toolbar--brand">
          <SpikatelBrand
            inverse
            title="Инвентаризация ЦОД"
          />
          <TelegramFullscreenButton />
        </div>

        <div className="detail-header__row detail-header__row--title">
          {!telegramOwnsBack ? (
            <button
              aria-label="Назад"
              className="icon-button icon-button--light"
              onClick={back}
              type="button"
            >
              ←
            </button>
          ) : null}

          <div className="detail-header__title">
            <span className="section-kicker">
              Каталог
            </span>

            <h1>
              {itemId
                ? "Редактировать оборудование"
                : "Добавить оборудование"}
            </h1>
          </div>
        </div>
      </header>

      <div className="catalog-page__body">
        <form
          autoComplete="off"
          className="catalog-form"
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
            ) {
              return;
            }

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
          <fieldset
            className="detail-panel"
            disabled={mutation.isPending}
          >
            <h2 className="catalog-form__panel-title">
              Основное
            </h2>

            {!itemId ? (
              <>
                <label className="catalog-form__field">
                  Раздел
                  <select
                    onChange={(event) => {
                      setFamily(event.target.value);
                      setManufacturerInput("");

                      const options =
                        categories.data?.filter(
                          (category) =>
                            category.parent_id
                            === event.target.value,
                        ) ?? [];

                      update({
                        ...empty,
                        category:
                          options.length === 1
                            ? options[0].key
                            : "",
                      });
                    }}
                    required
                    value={familyId}
                  >
                    <option value="">
                      Выберите раздел
                    </option>

                    {categories.data
                      ?.filter(
                        (category) =>
                          category.parent_id === null,
                      )
                      .map((category) => (
                        <option
                          key={category.id}
                          value={category.id}
                        >
                          {category.display_name}
                        </option>
                      ))}
                  </select>
                </label>

                <label className="catalog-form__field">
                  Категория
                  <select
                    onChange={(event) => {
                      setManufacturerInput("");
                      update({
                        ...empty,
                        category: event.target.value,
                      });
                    }}
                    required
                    value={draft.category}
                  >
                    <option value="">
                      Выберите категорию
                    </option>

                    {leaves.map((category) => (
                      <option
                        key={category.id}
                        value={category.key}
                      >
                        {category.display_name}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            ) : (
              <p>{selected?.display_name}</p>
            )}

            {categories.isError ? (
              <p role="alert">
                Не удалось загрузить категории.{" "}
                <button
                  onClick={() => void categories.refetch()}
                  type="button"
                >
                  Повторить
                </button>
              </p>
            ) : null}

            {identityRequired ? (
              <>
                <SuggestionInput
                  label="Производитель"
                  loading={manufacturers.isFetching}
                  onChange={(value) => {
                    setManufacturerInput(value);

                    if (draft.manufacturer) {
                      update({
                        manufacturer: "",
                      });
                    }
                  }}
                  onSelect={(option) => {
                    setManufacturerInput(option.label);
                    update({
                      manufacturer: option.key,
                    });
                  }}
                  options={manufacturerOptions}
                  required
                  value={manufacturerInput}
                />

                {manufacturers.isError ? (
                  <p role="alert">
                    Не удалось загрузить производителей.{" "}
                    <button
                      onClick={() =>
                        void manufacturers.refetch()
                      }
                      type="button"
                    >
                      Повторить
                    </button>
                  </p>
                ) : null}

                <SuggestionInput
                  label="Модель"
                  loading={modelMatches.isFetching}
                  maxLength={255}
                  onChange={(value) =>
                    update({
                      model: value,
                    })
                  }
                  options={modelOptions}
                  required
                  value={draft.model}
                />

                <details>
                  <summary>Добавить производителя</summary>

                  <label className="catalog-form__field">
                    Название производителя
                    <input
                      autoComplete="off"
                      maxLength={255}
                      onChange={(event) =>
                        setManufacturerName(
                          event.target.value,
                        )
                      }
                      value={manufacturerName}
                    />
                  </label>

                  <button
                    className="button"
                    disabled={
                      !manufacturerName.trim()
                      || makerMutation.isPending
                    }
                    onClick={() =>
                      makerMutation.mutate()
                    }
                    type="button"
                  >
                    Создать производителя
                  </button>

                  {makerMutation.isError ? (
                    <p role="alert">
                      Не удалось создать производителя.
                      Возможно, он уже существует.
                    </p>
                  ) : null}
                </details>
              </>
            ) : null}

            <SuggestionInput
              className="catalog-form__field--wide"
              label="Название оборудования"
              loading={nameMatches.isFetching}
              maxLength={255}
              onChange={(value) =>
                update({
                  name: value,
                })
              }
              options={nameOptions}
              required
              value={draft.name}
            />
          </fieldset>

          {draft.category ? (
            <fieldset
              className="detail-panel"
              disabled={mutation.isPending}
            >
              <h2 className="catalog-form__panel-title">
                Характеристики
              </h2>

              {schema.isPending ? (
                <p>Загружаем поля…</p>
              ) : null}

              {schema.isError ? (
                <p role="alert">
                  Не удалось загрузить поля.{" "}
                  <button
                    onClick={() => void schema.refetch()}
                    type="button"
                  >
                    Повторить
                  </button>
                </p>
              ) : null}

              {definitions.map((attribute) => (
                <SmartAttributeControl
                  attribute={attribute}
                  category={draft.category}
                  error={errors[attribute.key]}
                  key={attribute.key}
                  onChange={(value) => {
                    const attributes = {
                      ...draft.attributes,
                    };

                    if (value === undefined) {
                      delete attributes[attribute.key];
                    } else {
                      attributes[attribute.key] = value;
                    }

                    update({
                      attributes,
                    });
                  }}
                  value={draft.attributes[attribute.key]}
                />
              ))}
            </fieldset>
          ) : null}

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

          <button
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
          </button>
        </form>
      </div>
    </main>
  );
}
