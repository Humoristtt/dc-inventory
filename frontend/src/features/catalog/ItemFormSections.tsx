import {
  Button,
  Input,
  Select,
} from "../../shared/ui";
import {
  SuggestionInput,
  type SuggestionOption,
} from "./SuggestionInput";
import {
  SmartAttributeControl,
  type ItemFormDraft,
} from "./itemFormSupport";
import type {
  CategoryAttribute,
  CategorySummary,
} from "../../shared/api/catalog";

type BasicFieldsProps = {
  categories: readonly CategorySummary[];
  categoriesError: boolean;
  creatingManufacturer: boolean;
  createManufacturerError: boolean;
  disabled: boolean;
  draft: ItemFormDraft;
  editing: boolean;
  familyId: string;
  identityRequired: boolean;
  leaves: readonly CategorySummary[];
  manufacturerInput: string;
  manufacturerLoading: boolean;
  manufacturerName: string;
  manufacturerOptions: readonly SuggestionOption[];
  manufacturerSuggestionsError: boolean;
  modelLoading: boolean;
  modelOptions: readonly SuggestionOption[];
  nameLoading: boolean;
  nameOptions: readonly SuggestionOption[];
  selected: CategorySummary | undefined;
  onCategoryChange: (value: string) => void;
  onCreateManufacturer: () => void;
  onFamilyChange: (value: string) => void;
  onManufacturerInputChange: (value: string) => void;
  onManufacturerNameChange: (value: string) => void;
  onManufacturerSelect: (option: SuggestionOption) => void;
  onModelChange: (value: string) => void;
  onNameChange: (value: string) => void;
  onRetryCategories: () => void;
  onRetryManufacturers: () => void;
};

export function ItemFormBasicFields({
  categories,
  categoriesError,
  creatingManufacturer,
  createManufacturerError,
  disabled,
  draft,
  editing,
  familyId,
  identityRequired,
  leaves,
  manufacturerInput,
  manufacturerLoading,
  manufacturerName,
  manufacturerOptions,
  manufacturerSuggestionsError,
  modelLoading,
  modelOptions,
  nameLoading,
  nameOptions,
  selected,
  onCategoryChange,
  onCreateManufacturer,
  onFamilyChange,
  onManufacturerInputChange,
  onManufacturerNameChange,
  onManufacturerSelect,
  onModelChange,
  onNameChange,
  onRetryCategories,
  onRetryManufacturers,
}: BasicFieldsProps) {
  return (
    <fieldset
      className="detail-panel"
      disabled={disabled}
    >
      <h2 className="catalog-form__panel-title">
        Основное
      </h2>

      {!editing ? (
        <>
          <label className="catalog-form__field">
            Раздел
            <Select
              onChange={(event) =>
                onFamilyChange(
                  event.target.value,
                )
              }
              required
              value={familyId}
            >
              <option value="">
                Выберите раздел
              </option>

              {categories
                .filter(
                  (category) =>
                    category.parent_id
                    === null,
                )
                .map((category) => (
                  <option
                    key={category.id}
                    value={category.id}
                  >
                    {
                      category.display_name
                    }
                  </option>
                ))}
            </Select>
          </label>

          <label className="catalog-form__field">
            Категория
            <Select
              onChange={(event) =>
                onCategoryChange(
                  event.target.value,
                )
              }
              required
              value={draft.category}
            >
              <option value="">
                Выберите категорию
              </option>

              {leaves.map(
                (category) => (
                  <option
                    key={category.id}
                    value={category.key}
                  >
                    {
                      category.display_name
                    }
                  </option>
                ),
              )}
            </Select>
          </label>
        </>
      ) : (
        <p>{selected?.display_name}</p>
      )}

      {categoriesError ? (
        <p role="alert">
          Не удалось загрузить категории.{" "}
          <Button
            onClick={onRetryCategories}
            type="button"
          >
            Повторить
          </Button>
        </p>
      ) : null}

      {identityRequired ? (
        <>
          <SuggestionInput
            label="Производитель"
            loading={manufacturerLoading}
            onChange={
              onManufacturerInputChange
            }
            onSelect={
              onManufacturerSelect
            }
            options={[
              ...manufacturerOptions,
            ]}
            required
            value={manufacturerInput}
          />

          {manufacturerSuggestionsError ? (
            <p role="alert">
              Не удалось загрузить
              производителей.{" "}
              <Button
                onClick={
                  onRetryManufacturers
                }
                type="button"
              >
                Повторить
              </Button>
            </p>
          ) : null}

          <SuggestionInput
            label="Модель"
            loading={modelLoading}
            maxLength={255}
            onChange={onModelChange}
            options={[...modelOptions]}
            required
            value={draft.model}
          />

          <details>
            <summary>
              Добавить производителя
            </summary>

            <label className="catalog-form__field">
              Название производителя
              <Input
                maxLength={255}
                onChange={(event) =>
                  onManufacturerNameChange(
                    event.target.value,
                  )
                }
                value={manufacturerName}
              />
            </label>

            <Button
              className="button button--dark catalog-form__manufacturer-create"
              disabled={
                !manufacturerName.trim()
                || creatingManufacturer
              }
              onClick={
                onCreateManufacturer
              }
              type="button"
            >
              Создать производителя
            </Button>

            {createManufacturerError ? (
              <p role="alert">
                Не удалось создать
                производителя. Возможно,
                он уже существует.
              </p>
            ) : null}
          </details>
        </>
      ) : null}

      <SuggestionInput
        className="catalog-form__field--wide"
        label="Название оборудования"
        loading={nameLoading}
        maxLength={255}
        onChange={onNameChange}
        options={[...nameOptions]}
        required
        value={draft.name}
      />
    </fieldset>
  );
}

type AttributeFieldsProps = {
  category: string;
  definitions: readonly CategoryAttribute[];
  disabled: boolean;
  errors: Readonly<Record<string, string>>;
  loading: boolean;
  loadError: boolean;
  values: ItemFormDraft["attributes"];
  onChange: (
    key: string,
    value:
      | string
      | boolean
      | undefined,
  ) => void;
  onRetry: () => void;
};

export function ItemFormAttributeFields({
  category,
  definitions,
  disabled,
  errors,
  loading,
  loadError,
  values,
  onChange,
  onRetry,
}: AttributeFieldsProps) {
  if (!category) {
    return null;
  }

  return (
    <fieldset
      className="detail-panel"
      disabled={disabled}
    >
      <h2 className="catalog-form__panel-title">
        Характеристики
      </h2>

      {loading ? (
        <p>Загружаем поля…</p>
      ) : null}

      {loadError ? (
        <p role="alert">
          Не удалось загрузить поля.{" "}
          <Button
            onClick={onRetry}
            type="button"
          >
            Повторить
          </Button>
        </p>
      ) : null}

      {definitions.map(
        (attribute) => (
          <SmartAttributeControl
            attribute={attribute}
            category={category}
            error={
              errors[attribute.key]
            }
            key={attribute.key}
            onChange={(value) =>
              onChange(
                attribute.key,
                value,
              )
            }
            value={
              values[attribute.key]
            }
          />
        ),
      )}
    </fieldset>
  );
}
