import {
  Button,
  Input,
  Select,
} from "../../shared/ui";
import {
  AttributeControl,
} from "../catalog/AttributeControl";
import type {
  AttributeDraft,
} from "../catalog/itemForm";
import {
  catalogItemLabel,
} from "./catalogItemSearch";
import type {
  CatalogItemListEntry,
  CategoryAttribute,
  CategorySummary,
  Manufacturer,
} from "../../shared/api/catalog";

export type CategoryGroup = {
  family: CategorySummary;
  children: CategorySummary[];
};

export function ExistingItemFields({
  catalogCategory,
  categoryGroups,
  existingItemId,
  hasNextPage,
  itemOptions,
  loading,
  loadingNext,
  search,
  searchEmpty,
  onCatalogCategoryChange,
  onExistingItemChange,
  onLoadMore,
  onSearchChange,
}: {
  catalogCategory: string;
  categoryGroups:
    readonly CategoryGroup[];
  existingItemId: string;
  hasNextPage: boolean;
  itemOptions:
    readonly CatalogItemListEntry[];
  loading: boolean;
  loadingNext: boolean;
  search: string;
  searchEmpty: boolean;
  onCatalogCategoryChange:
    (value: string) => void;
  onExistingItemChange:
    (value: string) => void;
  onLoadMore: () => void;
  onSearchChange:
    (value: string) => void;
}) {
  return (
    <div className="procurement-fields">
      <label>
        Категория
        <Select
          onChange={(event) =>
            onCatalogCategoryChange(
              event.target.value,
            )
          }
          value={catalogCategory}
        >
          <option value="">
            Все категории и подкатегории
          </option>

          {categoryGroups.map(
            ({ family, children }) => (
              <optgroup
                key={family.id}
                label={
                  family.display_name
                }
              >
                <option
                  value={family.key}
                >
                  Все: {
                    family.display_name
                  }
                </option>

                {children.map(
                  (entry) => (
                    <option
                      key={entry.id}
                      value={entry.key}
                    >
                      {
                        entry.display_name
                      }
                    </option>
                  ),
                )}
              </optgroup>
            ),
          )}
        </Select>
      </label>

      <label>
        Поиск по каталогу
        <Input
          onChange={(event) =>
            onSearchChange(
              event.target.value,
            )
          }
          value={search}
        />
      </label>

      <label>
        Позиция
        <Select
          onChange={(event) =>
            onExistingItemChange(
              event.target.value,
            )
          }
          value={existingItemId}
        >
          <option value="">
            {
              loading
                ? "Загружаем каталог…"
                : "Выберите"
            }
          </option>

          {itemOptions.map(
            (item) => (
              <option
                key={item.id}
                value={item.id}
              >
                {
                  catalogItemLabel(
                    item,
                  )
                }
              </option>
            ),
          )}
        </Select>
      </label>

      {searchEmpty ? (
        <p className="empty-state">
          Совпадений и похожих
          позиций не найдено.
        </p>
      ) : null}

      {hasNextPage ? (
        <Button
          className="button button--load-more"
          disabled={loadingNext}
          onClick={onLoadMore}
        >
          {
            loadingNext
              ? "Загружаем…"
              : "Показать ещё"
          }
        </Button>
      ) : null}
    </div>
  );
}

export function ProposedItemFields({
  attributes,
  category,
  definitions,
  identityRequired,
  leaves,
  manufacturerId,
  manufacturerOptions,
  manufacturerSearch,
  manufacturersHaveNextPage,
  manufacturersLoadingNext,
  model,
  name,
  onAttributeChange,
  onCategoryChange,
  onLoadMoreManufacturers,
  onManufacturerChange,
  onManufacturerSearchChange,
  onModelChange,
  onNameChange,
}: {
  attributes: AttributeDraft;
  category: string;
  definitions:
    readonly CategoryAttribute[];
  identityRequired: boolean;
  leaves:
    readonly CategorySummary[];
  manufacturerId: string;
  manufacturerOptions:
    readonly Manufacturer[];
  manufacturerSearch: string;
  manufacturersHaveNextPage: boolean;
  manufacturersLoadingNext: boolean;
  model: string;
  name: string;
  onAttributeChange: (
    key: string,
    value:
      | string
      | boolean
      | undefined,
  ) => void;
  onCategoryChange:
    (value: string) => void;
  onLoadMoreManufacturers:
    () => void;
  onManufacturerChange:
    (value: string) => void;
  onManufacturerSearchChange:
    (value: string) => void;
  onModelChange:
    (value: string) => void;
  onNameChange:
    (value: string) => void;
}) {
  return (
    <div className="procurement-fields">
      <label>
        Категория
        <Select
          onChange={(event) =>
            onCategoryChange(
              event.target.value,
            )
          }
          value={category}
        >
          <option value="">
            Выберите
          </option>
          {leaves.map((entry) => (
            <option
              key={entry.id}
              value={entry.key}
            >
              {entry.display_name}
            </option>
          ))}
        </Select>
      </label>

      {identityRequired ? (
        <>
          <label>
            Поиск производителя
            <Input
              onChange={(event) =>
                onManufacturerSearchChange(
                  event.target.value,
                )
              }
              value={
                manufacturerSearch
              }
            />
          </label>

          <label>
            Производитель
            <Select
              onChange={(event) =>
                onManufacturerChange(
                  event.target.value,
                )
              }
              value={manufacturerId}
            >
              <option value="">
                Выберите
              </option>
              {manufacturerOptions.map(
                (entry) => (
                  <option
                    key={entry.id}
                    value={entry.id}
                  >
                    {entry.name}
                  </option>
                ),
              )}
            </Select>
          </label>

          {manufacturersHaveNextPage ? (
            <Button
              className="button button--load-more"
              disabled={
                manufacturersLoadingNext
              }
              onClick={
                onLoadMoreManufacturers
              }
            >
              {
                manufacturersLoadingNext
                  ? "Загружаем производителей…"
                  : "Показать ещё производителей"
              }
            </Button>
          ) : null}
        </>
      ) : null}

      <label>
        Название
        <Input
          maxLength={255}
          onChange={(event) =>
            onNameChange(
              event.target.value,
            )
          }
          value={name}
        />
      </label>

      {identityRequired ? (
        <label>
          Модель
          <Input
            maxLength={255}
            onChange={(event) =>
              onModelChange(
                event.target.value,
              )
            }
            value={model}
          />
        </label>
      ) : null}

      {definitions.map(
        (definition) => (
          <AttributeControl
            attribute={definition}
            error={undefined}
            key={definition.id}
            onChange={(value) =>
              onAttributeChange(
                definition.key,
                value,
              )
            }
            value={
              attributes[
                definition.key
              ]
            }
          />
        ),
      )}
    </div>
  );
}
