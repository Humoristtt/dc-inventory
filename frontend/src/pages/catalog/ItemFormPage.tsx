import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  type FormEvent,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Navigate,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

import {
  CatalogErrorState,
  CatalogListSkeleton,
} from "../../features/catalog/CatalogState";
import {
  DebouncedSearchField,
} from "../../features/catalog/DebouncedSearchField";
import {
  type AttributeDraft,
  attributesEqual,
  draftAttributesFromItem,
  validateDraftAttributes,
} from "../../features/catalog/itemForm";
import { useAuthState } from "../../features/auth/useAuthState";
import { useInternalBackNavigation } from "../../features/navigation/useTelegramNavigation";
import {
  ApiRequestError,
} from "../../shared/api/auth";
import {
  checkCatalogDuplicates,
  createCatalogItem,
  createCatalogManufacturer,
  getCatalogCategories,
  getCatalogCategory,
  getCatalogItem,
  getCatalogManufacturers,
  patchCatalogItem,
  type AccountingMode,
  type CatalogItem,
  type CategoryAttribute,
  type DuplicateCandidate,
  type ItemPatchPayload,
  type ItemWritePayload,
  type ItemManufacturer,
} from "../../shared/api/catalog";
import "../../features/catalog/admin-catalog.css";

type CommonDraft = {
  categoryKey: string;
  manufacturerId: string;
  name: string;
  model: string;
  manufacturerPartNumber: string;
  internalCode: string;
  description: string;
  accountingMode: AccountingMode;
  comment: string;
  datasheetUrl: string;
  technicalDataSource: string;
};

type DuplicateReview = {
  candidates: DuplicateCandidate[];
  identityKey: string;
};

const emptyDraft: CommonDraft = {
  categoryKey: "",
  manufacturerId: "",
  name: "",
  model: "",
  manufacturerPartNumber: "",
  internalCode: "",
  description: "",
  accountingMode: "QUANTITY",
  comment: "",
  datasheetUrl: "",
  technicalDataSource: "",
};

function draftFromItem(item: CatalogItem): CommonDraft {
  return {
    categoryKey: item.category.key,
    manufacturerId: item.manufacturer?.id ?? "",
    name: item.name,
    model: item.model ?? "",
    manufacturerPartNumber: item.manufacturer_part_number ?? "",
    internalCode: item.internal_code ?? "",
    description: item.description ?? "",
    accountingMode: item.accounting_mode,
    comment: item.comment ?? "",
    datasheetUrl: item.datasheet_url ?? "",
    technicalDataSource: item.technical_data_source ?? "",
  };
}

function nullable(value: string): string | null {
  return value.trim() === "" ? null : value;
}

const duplicateIdentityFields = new Set<keyof CommonDraft>([
  "categoryKey",
  "manufacturerId",
  "name",
  "model",
  "manufacturerPartNumber",
]);

function duplicateIdentity(draft: CommonDraft) {
  return {
    category_key: draft.categoryKey,
    manufacturer_id: draft.manufacturerId || null,
    manufacturer_part_number: nullable(draft.manufacturerPartNumber),
    name: draft.name,
    model: nullable(draft.model),
  };
}

function duplicateIdentityKey(draft: CommonDraft): string {
  return JSON.stringify(duplicateIdentity(draft));
}

const staleDuplicateCheckMessage =
  "Данные формы изменились во время проверки дублей. Проверьте их и повторите проверку.";

function errorMessage(error: unknown): string {
  if (!(error instanceof ApiRequestError)) {
    return "Не удалось сохранить изменения. Проверьте соединение и повторите.";
  }
  if (error.code === "catalog_conflict") {
    return "Данные конфликтуют с существующей позицией. Проверьте внутренний код и производителя.";
  }
  if (error.status === 403) {
    return "Недостаточно прав для изменения каталога.";
  }
  if (error.status === 422) {
    return "Backend отклонил данные. Проверьте обязательные поля и характеристики.";
  }
  return "Не удалось сохранить изменения. Повторите попытку.";
}

function duplicateReason(candidate: DuplicateCandidate): string {
  return candidate.reason === "same_category_manufacturer_mpn"
    ? "Совпадают категория, производитель и part number"
    : "Совпадают категория, производитель, название и модель";
}

type AttributeControlProps = {
  attribute: CategoryAttribute;
  error: string | undefined;
  onChange: (value: string | boolean | undefined) => void;
  value: string | boolean | undefined;
};

function AttributeControl({
  attribute,
  error,
  onChange,
  value,
}: AttributeControlProps) {
  const controlId = `attribute-${attribute.key}`;
  const errorId = `${controlId}-error`;
  const maxLength = attribute.validation_metadata?.max_length;
  const multiline = attribute.data_type === "TEXT"
    && (
      attribute.validation_metadata?.preserve_whitespace === true
      || (typeof maxLength === "number" && maxLength > 255)
    );
  const label = (
    <span className="catalog-form__label">
      {attribute.label}
      {attribute.required ? <b aria-label="обязательное поле">*</b> : null}
      {attribute.unit ? <small>{attribute.unit}</small> : null}
    </span>
  );

  if (attribute.data_type === "BOOLEAN") {
    const specified = typeof value === "boolean";
    return (
      <div className="catalog-form__field catalog-form__field--boolean">
        {label}
        <div className="catalog-form__boolean-row">
          <label className="catalog-switch" htmlFor={controlId}>
            <input
              aria-describedby={error ? errorId : undefined}
              checked={value === true}
              id={controlId}
              onChange={(event) => onChange(event.target.checked)}
              type="checkbox"
            />
            <span aria-hidden="true" />
            <strong>{specified ? (value ? "Да" : "Нет") : "Не указано"}</strong>
          </label>
          {specified && !attribute.required ? (
            <button className="text-button" onClick={() => onChange(undefined)} type="button">
              Сбросить
            </button>
          ) : null}
        </div>
        {error ? <small className="catalog-form__error" id={errorId}>{error}</small> : null}
      </div>
    );
  }

  if (attribute.data_type === "ENUM") {
    return (
      <label className="catalog-form__field" htmlFor={controlId}>
        {label}
        <select
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error !== undefined}
          id={controlId}
          onChange={(event) => onChange(event.target.value)}
          value={typeof value === "string" ? value : ""}
        >
          <option value="">Не указано</option>
          {(attribute.allowed_values ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        {error ? <small className="catalog-form__error" id={errorId}>{error}</small> : null}
      </label>
    );
  }

  const inputMode = attribute.data_type === "INTEGER" ? "numeric" : "decimal";
  const inputValue = typeof value === "string" ? value : "";
  return (
    <label className="catalog-form__field" htmlFor={controlId}>
      {label}
      {multiline ? (
        <textarea
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error !== undefined}
          id={controlId}
          onChange={(event) => onChange(event.target.value)}
          rows={attribute.key === "reach_profile" ? 4 : 2}
          value={inputValue}
        />
      ) : (
        <input
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error !== undefined}
          id={controlId}
          inputMode={attribute.data_type === "TEXT" ? "text" : inputMode}
          onChange={(event) => onChange(event.target.value)}
          type="text"
          value={inputValue}
        />
      )}
      {error ? <small className="catalog-form__error" id={errorId}>{error}</small> : null}
    </label>
  );
}

export function ItemFormPage() {
  const { itemId } = useParams();
  const editing = itemId !== undefined;
  const authQuery = useAuthState();
  const navigate = useNavigate();
  const navigateBack = useInternalBackNavigation();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const requestedCategoryKey = searchParams.get("category") ?? "";
  const queryClient = useQueryClient();
  const [draftState, setDraftState] = useState<CommonDraft | null>(null);
  const [attributeDraftState, setAttributeDraftState] = useState<AttributeDraft | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [attributeErrors, setAttributeErrors] = useState<Record<string, string>>({});
  const [manufacturerFormOpen, setManufacturerFormOpen] = useState(false);
  const [manufacturerName, setManufacturerName] = useState("");
  const [manufacturerError, setManufacturerError] = useState<string | null>(null);
  const [manufacturerSearch, setManufacturerSearch] = useState("");
  const [selectedManufacturer, setSelectedManufacturer] =
    useState<ItemManufacturer | null>(null);
  const [duplicateReview, setDuplicateReview] = useState<DuplicateReview | null>(null);
  const [checkingDuplicates, setCheckingDuplicates] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const formRevisionRef = useRef(0);

  const itemQuery = useQuery({
    queryKey: ["catalog", "item", itemId],
    queryFn: ({ signal }) => getCatalogItem(itemId ?? "", signal),
    enabled: editing && itemId !== "",
  });
  const categoriesQuery = useQuery({
    queryKey: ["catalog", "categories"],
    queryFn: ({ signal }) => getCatalogCategories(signal),
    staleTime: 5 * 60_000,
  });
  const manufacturersQuery = useInfiniteQuery({
    queryKey: [
      "catalog",
      "manufacturers",
      manufacturerSearch.trim(),
    ],
    queryFn: ({ pageParam, signal }) => getCatalogManufacturers(
      {
        limit: 50,
        offset: pageParam,
        q: manufacturerSearch.trim() || undefined,
      },
      signal,
    ),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      if (lastPage.items.length === 0) {
        return undefined;
      }

      const nextOffset =
        lastPage.offset + lastPage.items.length;

      return nextOffset < lastPage.total
        ? nextOffset
        : undefined;
    },
    staleTime: 5 * 60_000,
  });
  const sortedCategories = useMemo(
    () => [...(categoriesQuery.data ?? [])].sort(
      (left, right) => left.sort_order - right.sort_order,
    ),
    [categoriesQuery.data],
  );
  const defaultCategory = sortedCategories.find(
    (category) => category.key === requestedCategoryKey,
  ) ?? sortedCategories[0];
  const initialDraft = editing && itemQuery.data !== undefined
    ? draftFromItem(itemQuery.data)
    : {
      ...emptyDraft,
      categoryKey: defaultCategory?.key ?? requestedCategoryKey,
      accountingMode: defaultCategory?.default_accounting_mode ?? "QUANTITY",
    };
  const draft = draftState ?? initialDraft;

  const manufacturerOptions = useMemo(() => {
    const byId = new Map<string, ItemManufacturer>();

    for (const page of manufacturersQuery.data?.pages ?? []) {
      for (const manufacturer of page.items) {
        byId.set(manufacturer.id, manufacturer);
      }
    }

    const editingManufacturer = itemQuery.data?.manufacturer;
    if (
      editingManufacturer !== null
      && editingManufacturer !== undefined
      && editingManufacturer.id === draft.manufacturerId
    ) {
      byId.set(editingManufacturer.id, editingManufacturer);
    }

    if (
      selectedManufacturer !== null
      && selectedManufacturer.id === draft.manufacturerId
    ) {
      byId.set(selectedManufacturer.id, selectedManufacturer);
    }

    return [...byId.values()].sort(
      (left, right) => left.name.localeCompare(
        right.name,
        "ru",
      ),
    );
  }, [
    draft.manufacturerId,
    itemQuery.data?.manufacturer,
    manufacturersQuery.data?.pages,
    selectedManufacturer,
  ]);

  const attributeDraft = attributeDraftState
    ?? (editing && itemQuery.data !== undefined
      ? draftAttributesFromItem(itemQuery.data)
      : {});
  const selectedCategoryKey = editing
    ? itemQuery.data?.category.key ?? ""
    : draft.categoryKey;
  const categoryQuery = useQuery({
    queryKey: ["catalog", "category", selectedCategoryKey],
    queryFn: ({ signal }) => getCatalogCategory(selectedCategoryKey, signal),
    enabled: selectedCategoryKey !== "",
    staleTime: 5 * 60_000,
  });

  const definitions = useMemo(
    () => [...(categoryQuery.data?.attributes ?? [])].sort(
      (left, right) => left.sort_order - right.sort_order,
    ),
    [categoryQuery.data?.attributes],
  );

  const saveMutation = useMutation({
    mutationFn: (
      payload: ItemWritePayload | { itemId: string; patch: ItemPatchPayload },
    ) => "itemId" in payload
      ? patchCatalogItem(payload.itemId, payload.patch)
      : createCatalogItem(payload),
    onSuccess: (item) => {
      queryClient.setQueryData(["catalog", "item", item.id], item);
      void queryClient.invalidateQueries({ queryKey: ["catalog", "items"] });
      void queryClient.invalidateQueries({ queryKey: ["catalog", "facets"] });
      const from = typeof location.state === "object"
        && location.state !== null
        && typeof (location.state as { from?: unknown }).from === "string"
        ? (location.state as { from: string }).from
        : `/catalog/${encodeURIComponent(item.category.key)}`;
      navigate(`/catalog/items/${encodeURIComponent(item.id)}`, {
        replace: true,
        state: { from },
      });
    },
    onError: (error) => setSaveError(errorMessage(error)),
  });

  const manufacturerMutation = useMutation({
    mutationFn: (name: string) => createCatalogManufacturer(name),
    onSuccess: (manufacturer) => {
      formRevisionRef.current += 1;
      setDuplicateReview(null);
      setSelectedManufacturer(manufacturer);
      void queryClient.invalidateQueries({
        queryKey: ["catalog", "manufacturers"],
      });
      setDraftState((current) => ({
        ...(current ?? draft),
        manufacturerId: manufacturer.id,
      }));
      setManufacturerName("");
      setManufacturerError(null);
      setManufacturerFormOpen(false);
    },
    onError: (error) => {
      setManufacturerError(
        error instanceof ApiRequestError && error.status === 409
          ? "Такой производитель уже существует. Выберите его в списке."
          : "Не удалось создать производителя. Повторите попытку.",
      );
    },
  });

  if (authQuery.isPending || (editing && itemQuery.isPending)) {
    return (
      <main className="catalog-page detail-page">
        <header className="detail-header">
          <button aria-label="Назад" className="icon-button icon-button--light" onClick={navigateBack} type="button">←</button>
          <span>{editing ? "Редактирование" : "Новая позиция"}</span>
        </header>
        <div className="catalog-page__body"><CatalogListSkeleton count={2} /></div>
      </main>
    );
  }

  if (authQuery.data?.user.role !== "ADMIN") {
    return <Navigate replace to="/catalog" />;
  }

  if (editing && (itemQuery.isError || itemQuery.data === undefined)) {
    return (
      <main className="catalog-page detail-page">
        <header className="detail-header">
          <button aria-label="Назад" className="icon-button icon-button--light" onClick={navigateBack} type="button">←</button>
          <span>Редактирование</span>
        </header>
        <div className="catalog-page__body">
          <CatalogErrorState title="Не удалось загрузить позицию" onRetry={() => void itemQuery.refetch()} />
        </div>
      </main>
    );
  }

  const validate = () => {
    const commonErrors: Record<string, string> = {};
    if (draft.categoryKey === "") commonErrors.categoryKey = "Выберите категорию";
    if (draft.name.trim() === "") commonErrors.name = "Обязательное поле";
    if (draft.name.length > 255) commonErrors.name = "Не более 255 символов";
    if (draft.datasheetUrl.trim() !== "") {
      try {
        const url = new URL(draft.datasheetUrl);
        if (url.protocol !== "http:" && url.protocol !== "https:") {
          commonErrors.datasheetUrl = "Разрешены только http/https ссылки";
        }
      } catch {
        commonErrors.datasheetUrl = "Введите корректную http/https ссылку";
      }
    }
    const attributes = validateDraftAttributes(definitions, attributeDraft);
    setFieldErrors(commonErrors);
    setAttributeErrors(attributes.errors);
    if (Object.keys(commonErrors).length > 0 || Object.keys(attributes.errors).length > 0) {
      return null;
    }
    return attributes.values;
  };

  const writePayload = (attributes: Record<string, string | number | boolean>): ItemWritePayload => ({
    category_key: draft.categoryKey,
    manufacturer_id: draft.manufacturerId || null,
    name: draft.name,
    model: nullable(draft.model),
    manufacturer_part_number: nullable(draft.manufacturerPartNumber),
    internal_code: nullable(draft.internalCode),
    description: nullable(draft.description),
    accounting_mode: draft.accountingMode,
    comment: nullable(draft.comment),
    datasheet_url: nullable(draft.datasheetUrl),
    technical_data_source: nullable(draft.technicalDataSource),
    attributes,
  });

  const save = (attributes: Record<string, string | number | boolean>) => {
    setSaveError(null);
    if (!editing) {
      saveMutation.mutate(writePayload(attributes));
      return;
    }
    const item = itemQuery.data;
    if (item === undefined) return;
    const patch: ItemPatchPayload = {};
    const comparisons: Array<[
      keyof ItemPatchPayload,
      string | null,
      string | null,
    ]> = [
      ["manufacturer_id", draft.manufacturerId || null, item.manufacturer?.id ?? null],
      ["name", draft.name, item.name],
      ["model", nullable(draft.model), item.model],
      ["manufacturer_part_number", nullable(draft.manufacturerPartNumber), item.manufacturer_part_number],
      ["internal_code", nullable(draft.internalCode), item.internal_code],
      ["description", nullable(draft.description), item.description],
      ["comment", nullable(draft.comment), item.comment],
      ["datasheet_url", nullable(draft.datasheetUrl), item.datasheet_url],
      ["technical_data_source", nullable(draft.technicalDataSource), item.technical_data_source],
    ];
    for (const [key, next, previous] of comparisons) {
      if (next !== previous) {
        Object.assign(patch, { [key]: next });
      }
    }
    if (!attributesEqual(attributes, item.attributes)) {
      patch.attributes = attributes;
    }
    saveMutation.mutate({ itemId: item.id, patch });
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (saveMutation.isPending || checkingDuplicates) return;
    const attributes = validate();
    if (attributes === null) return;
    const editingItem = editing ? itemQuery.data : undefined;
    const checkedIdentity = duplicateIdentity(draft);
    const checkedIdentityKey = JSON.stringify(checkedIdentity);

    if (
      editingItem !== undefined
      && checkedIdentityKey
        === duplicateIdentityKey(draftFromItem(editingItem))
    ) {
      save(attributes);
      return;
    }

    setSaveError(null);
    setDuplicateReview(null);

    const checkedRevision = formRevisionRef.current;

    setCheckingDuplicates(true);
    try {
      const result = await checkCatalogDuplicates({
        ...checkedIdentity,
        ...(editingItem !== undefined
          ? { exclude_item_id: editingItem.id }
          : {}),
      });

      if (formRevisionRef.current !== checkedRevision) {
        setSaveError(staleDuplicateCheckMessage);
        return;
      }

      if (result.candidates.length > 0) {
        setDuplicateReview({
          candidates: result.candidates,
          identityKey: checkedIdentityKey,
        });
      } else {
        save(attributes);
      }
    } catch (error) {
      if (formRevisionRef.current === checkedRevision) {
        setSaveError(errorMessage(error));
      }
    } finally {
      setCheckingDuplicates(false);
    }
  };

  const updateDraft = <K extends keyof CommonDraft>(key: K, value: CommonDraft[K]) => {
    formRevisionRef.current += 1;
    if (duplicateIdentityFields.has(key)) {
      setDuplicateReview(null);
    }
    setDraftState((current) => ({ ...(current ?? draft), [key]: value }));
    setFieldErrors((current) => ({ ...current, [key]: "" }));
    setSaveError(null);
  };
  const pending = saveMutation.isPending || checkingDuplicates;

  return (
    <main className="catalog-page detail-page catalog-form-page">
      <header className="detail-header">
        <button aria-label="Назад" className="icon-button icon-button--light" onClick={navigateBack} type="button">←</button>
        <span>{editing ? "Редактирование позиции" : "Новая позиция"}</span>
        <span className="status-badge">ADMIN</span>
      </header>
      <div className="catalog-form-page__intro">
        <span className="section-kicker">Управление каталогом</span>
        <h1>{editing ? "Изменить позицию" : "Создать позицию"}</h1>
        <p>Поля характеристик формируются из актуальной схемы выбранной категории.</p>
      </div>

      <form className="catalog-form" noValidate onSubmit={(event) => void handleSubmit(event)}>
        <section className="catalog-form__section">
          <div className="catalog-form__section-title">
            <span>01</span><div><h2>Основное</h2><p>Категория и идентификация позиции</p></div>
          </div>
          {categoriesQuery.isError ? (
            <CatalogErrorState title="Не удалось загрузить категории" onRetry={() => void categoriesQuery.refetch()} />
          ) : (
            <label className="catalog-form__field" htmlFor="item-category">
              <span className="catalog-form__label">Категория <b>*</b></span>
              <select
                aria-invalid={fieldErrors.categoryKey !== undefined}
                disabled={editing || categoriesQuery.isPending}
                id="item-category"
                onChange={(event) => {
                  const category = categoriesQuery.data?.find((entry) => entry.key === event.target.value);
                  setAttributeDraftState({});
                  updateDraft("categoryKey", event.target.value);
                  if (category !== undefined) updateDraft("accountingMode", category.default_accounting_mode);
                }}
                value={draft.categoryKey}
              >
                <option value="">Выберите категорию</option>
                {(categoriesQuery.data ?? []).map((category) => (
                  <option key={category.id} value={category.key}>{category.display_name}</option>
                ))}
              </select>
              {fieldErrors.categoryKey ? <small className="catalog-form__error">{fieldErrors.categoryKey}</small> : null}
            </label>
          )}

          <div className="catalog-form__field">
            <label htmlFor="item-manufacturer">
              <span className="catalog-form__label">Производитель</span>
            </label>

            <div className="manufacturer-picker">
              <DebouncedSearchField
                busy={manufacturersQuery.isFetching}
                committedValue={manufacturerSearch}
                label="Поиск производителя"
                onCommit={setManufacturerSearch}
                placeholder="Начните вводить название"
              />

              <div className="catalog-form__inline-control">
                <select
                  disabled={
                    manufacturersQuery.isPending
                    && manufacturerOptions.length === 0
                  }
                  id="item-manufacturer"
                  onChange={(event) => {
                    const manufacturerId = event.target.value;

                    setSelectedManufacturer(
                      manufacturerOptions.find(
                        (manufacturer) =>
                          manufacturer.id === manufacturerId,
                      ) ?? null,
                    );

                    updateDraft(
                      "manufacturerId",
                      manufacturerId,
                    );
                  }}
                  value={draft.manufacturerId}
                >
                  <option value="">Не указан</option>

                  {manufacturerOptions.map((manufacturer) => (
                    <option
                      key={manufacturer.id}
                      value={manufacturer.id}
                    >
                      {manufacturer.name}
                    </option>
                  ))}
                </select>

                <button
                  className="button button--ghost catalog-form__inline-button"
                  onClick={() => {
                    setManufacturerFormOpen((open) => !open);
                    setManufacturerError(null);
                  }}
                  type="button"
                >
                  + Новый
                </button>
              </div>

              {manufacturersQuery.hasNextPage ? (
                <button
                  className="text-button manufacturer-picker__more"
                  disabled={manufacturersQuery.isFetchingNextPage}
                  onClick={() =>
                    void manufacturersQuery.fetchNextPage()}
                  type="button"
                >
                  {manufacturersQuery.isFetchingNextPage
                    ? "Загрузка…"
                    : "Показать ещё производителей"}
                </button>
              ) : null}
            </div>
            {manufacturersQuery.isError ? (
              <div className="catalog-form__inline-error" role="alert">
                <span>Список производителей недоступен.</span>
                <button className="text-button" onClick={() => void manufacturersQuery.refetch()} type="button">Повторить</button>
              </div>
            ) : null}
            {manufacturerFormOpen ? (
              <div className="inline-manufacturer">
                <label htmlFor="new-manufacturer">Название нового производителя</label>
                <div className="catalog-form__inline-control">
                  <input
                    autoComplete="organization"
                    id="new-manufacturer"
                    maxLength={255}
                    onChange={(event) => {
                      setManufacturerName(event.target.value);
                      setManufacturerError(null);
                    }}
                    value={manufacturerName}
                  />
                  <button
                    className="button button--dark catalog-form__inline-button"
                    disabled={manufacturerMutation.isPending || manufacturerName.trim() === ""}
                    onClick={() => manufacturerMutation.mutate(manufacturerName)}
                    type="button"
                  >
                    {manufacturerMutation.isPending ? "Создаём…" : "Создать"}
                  </button>
                </div>
                {manufacturerError ? <small className="catalog-form__error" role="alert">{manufacturerError}</small> : null}
                <p>Несохранённые поля позиции останутся на месте.</p>
              </div>
            ) : null}
          </div>

          <label className="catalog-form__field" htmlFor="item-name">
            <span className="catalog-form__label">Название <b>*</b></span>
            <input id="item-name" maxLength={255} onChange={(event) => updateDraft("name", event.target.value)} value={draft.name} />
            {fieldErrors.name ? <small className="catalog-form__error">{fieldErrors.name}</small> : null}
          </label>
          <div className="catalog-form__grid">
            <label className="catalog-form__field" htmlFor="item-model">
              <span className="catalog-form__label">Модель</span>
              <input id="item-model" maxLength={255} onChange={(event) => updateDraft("model", event.target.value)} value={draft.model} />
            </label>
            <label className="catalog-form__field" htmlFor="item-mpn">
              <span className="catalog-form__label">Part number</span>
              <input id="item-mpn" maxLength={255} onChange={(event) => updateDraft("manufacturerPartNumber", event.target.value)} value={draft.manufacturerPartNumber} />
            </label>
          </div>
          <label className="catalog-form__field" htmlFor="item-code">
            <span className="catalog-form__label">Внутренний код</span>
            <input id="item-code" maxLength={128} onChange={(event) => updateDraft("internalCode", event.target.value)} value={draft.internalCode} />
          </label>
          <label className="catalog-form__field" htmlFor="item-accounting">
            <span className="catalog-form__label">Способ учёта <b>*</b></span>
            <select
              disabled={editing}
              id="item-accounting"
              onChange={(event) => updateDraft("accountingMode", event.target.value as AccountingMode)}
              value={draft.accountingMode}
            >
              <option value="QUANTITY">Количественный</option>
              <option value="SERIAL">Серийный</option>
            </select>
            {editing ? <small className="catalog-form__hint">После создания способ учёта не меняется.</small> : null}
          </label>
        </section>

        <section className="catalog-form__section">
          <div className="catalog-form__section-title">
            <span>02</span><div><h2>Характеристики</h2><p>Порядок, типы и ограничения заданы metadata</p></div>
          </div>
          {categoryQuery.isPending ? <CatalogListSkeleton count={2} /> : null}
          {categoryQuery.isError ? (
            <CatalogErrorState title="Не удалось загрузить схему категории" onRetry={() => void categoryQuery.refetch()} />
          ) : null}
          {!categoryQuery.isPending && !categoryQuery.isError && definitions.length === 0 ? (
            <p className="catalog-form__empty">Для категории нет дополнительных характеристик.</p>
          ) : null}
          {definitions.map((attribute) => (
            <AttributeControl
              attribute={attribute}
              error={attributeErrors[attribute.key]}
              key={attribute.id}
              onChange={(value) => {
                formRevisionRef.current += 1;
                setAttributeDraftState((current) => {
                  const base = current ?? attributeDraft;
                  if (value === undefined) {
                    const next = { ...base };
                    delete next[attribute.key];
                    return next;
                  }
                  return { ...base, [attribute.key]: value };
                });
                setAttributeErrors((current) => ({ ...current, [attribute.key]: "" }));
                setSaveError(null);
              }}
              value={attributeDraft[attribute.key]}
            />
          ))}
        </section>

        <section className="catalog-form__section">
          <div className="catalog-form__section-title">
            <span>03</span><div><h2>Описание и источники</h2><p>Операционный контекст и документация</p></div>
          </div>
          <label className="catalog-form__field" htmlFor="item-description">
            <span className="catalog-form__label">Описание</span>
            <textarea id="item-description" onChange={(event) => updateDraft("description", event.target.value)} rows={4} value={draft.description} />
          </label>
          <label className="catalog-form__field" htmlFor="item-comment">
            <span className="catalog-form__label">Комментарий</span>
            <textarea id="item-comment" onChange={(event) => updateDraft("comment", event.target.value)} rows={3} value={draft.comment} />
          </label>
          <label className="catalog-form__field" htmlFor="item-datasheet">
            <span className="catalog-form__label">Datasheet URL</span>
            <input id="item-datasheet" inputMode="url" maxLength={2048} onChange={(event) => updateDraft("datasheetUrl", event.target.value)} value={draft.datasheetUrl} />
            {fieldErrors.datasheetUrl ? <small className="catalog-form__error">{fieldErrors.datasheetUrl}</small> : null}
          </label>
          <label className="catalog-form__field" htmlFor="item-source">
            <span className="catalog-form__label">Источник технических данных</span>
            <textarea id="item-source" onChange={(event) => updateDraft("technicalDataSource", event.target.value)} rows={3} value={draft.technicalDataSource} />
          </label>
        </section>

        {saveError ? <div className="catalog-form__submit-error" role="alert">{saveError}</div> : null}
        <div className="catalog-form__actions">
          <button className="button button--ghost" disabled={pending} onClick={navigateBack} type="button">Отмена</button>
          <button className="button button--dark" disabled={pending || categoryQuery.isPending || categoryQuery.isError} type="submit">
            {checkingDuplicates ? "Проверяем дубли…" : saveMutation.isPending ? "Сохраняем…" : editing ? "Сохранить" : "Проверить и создать"}
          </button>
        </div>
      </form>

      {duplicateReview !== null ? (
        <div className="sheet-backdrop" role="presentation">
          <section aria-labelledby="duplicate-title" aria-modal="true" className="sheet duplicate-sheet" role="dialog">
            <header className="sheet__header">
              <div><span className="section-kicker">Проверка дублей</span><h2 id="duplicate-title">Похожие позиции уже есть</h2></div>
              <button aria-label="Закрыть предупреждение" className="icon-button" data-escape-dismiss="" onClick={() => setDuplicateReview(null)} type="button">×</button>
            </header>
            <div className="sheet__body duplicate-sheet__body">
              <p>Проверьте совпадения. Введённые данные сохранены в форме.</p>
              {duplicateReview.candidates.map((candidate) => (
                <article className="duplicate-card" key={candidate.item_id}>
                  <strong>{candidate.manufacturer_name ?? "Без производителя"} · {candidate.model ?? candidate.name}</strong>
                  <span>{candidate.name}</span>
                  {candidate.manufacturer_part_number ? <span>PN {candidate.manufacturer_part_number}</span> : null}
                  <small>{duplicateReason(candidate)}</small>
                </article>
              ))}
            </div>
            <footer className="sheet__footer">
              <button className="button button--ghost" onClick={() => setDuplicateReview(null)} type="button">Вернуться</button>
              <button
                className="button button--dark"
                disabled={saveMutation.isPending}
                onClick={() => {
                  if (duplicateReview.identityKey !== duplicateIdentityKey(draft)) {
                    setDuplicateReview(null);
                    setSaveError(staleDuplicateCheckMessage);
                    return;
                  }

                  const attributes = validate();
                  if (attributes !== null) {
                    setDuplicateReview(null);
                    save(attributes);
                  }
                }}
                type="button"
              >
                {editing ? "Всё равно сохранить" : "Всё равно создать"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </main>
  );
}
