import { Button } from "../../shared/ui";

import {
  useState,
} from "react";
import {
  Navigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

import { useAuthState } from "../../features/auth/useAuthState";
import { hasCapability } from "../../shared/api/auth";
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
  type ItemFormDraft,
} from "../../features/catalog/itemFormSupport";
import {
  useItemFormBaseQueries,
  useItemFormSuggestions,
} from "../../features/catalog/useItemFormQueries";
import {
  useItemFormMutations,
} from "../../features/catalog/useItemFormMutations";
import { useInternalBackNavigation } from "../../features/navigation/useTelegramNavigation";
import { ApiRequestError } from "../../shared/api/auth";
import { PageHeader } from "../../shared/ui";
import { useTelegramWebApp } from "../../shared/telegram/useTelegramWebApp";

import "../../features/catalog/admin-catalog.css";
import "../../features/inventory/inventory.css";

export function ItemFormPage() {
  const webApp = useTelegramWebApp();
  const { itemId } = useParams();
  const [params] = useSearchParams();
  const auth = useAuthState();
  const back = useInternalBackNavigation();

  const [state, setState] = useState<ItemFormDraft | null>(null);
  const [family, setFamily] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [manufacturerName, setManufacturerName] = useState("");
  const [manufacturerInput, setManufacturerInput] = useState("");

  const procurementRequestId =
    params.get(
      "procurementRequestId",
    );
  const procurementLineId =
    params.get(
      "procurementLineId",
    );

  const {
    categories,
    item,
    procurement,
    procurementDraft,
    procurementLine,
  } = useItemFormBaseQueries({
    itemId,
    procurementLineId,
    procurementRequestId,
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

  const {
    definitions,
    manufacturerOptions,
    manufacturers,
    modelMatches,
    modelOptions,
    nameMatches,
    nameOptions,
    schema,
  } = useItemFormSuggestions({
    draft,
    identityRequired,
    manufacturerInput,
  });

  const {
    makerMutation,
    mutation,
    save,
  } = useItemFormMutations({
    itemId,
    manufacturerName,
    procurement:
      procurement.data,
    procurementLineId,
    procurementRequestId,
    onManufacturerCreated:
      (maker) => {
        setState({
          ...draft,
          manufacturer:
            maker.id,
        });
        setManufacturerInput(
          maker.name,
        );
        setManufacturerName("");
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
            ) {
              return;
            }

            save({
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
