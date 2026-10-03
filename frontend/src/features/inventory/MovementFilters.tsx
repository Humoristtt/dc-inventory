import {
  Button,
  Select,
} from "../../shared/ui";
import type {
  CategorySummary,
} from "../../shared/api/catalog";
import {
  movementLabels,
  type StorageLocation,
} from "../../shared/api/inventory";

type MovementActor = {
  id: string;
  name: string;
};

export function MovementFilters({
  actor,
  actors,
  canReadAll,
  categories,
  equipment,
  hasError,
  location,
  locations,
  movementType,
  period,
  onActorChange,
  onEquipmentChange,
  onLocationChange,
  onMovementTypeChange,
  onPeriodChange,
  onRetry,
}: {
  actor: string;
  actors:
    readonly MovementActor[];
  canReadAll: boolean;
  categories:
    readonly CategorySummary[];
  equipment: string;
  hasError: boolean;
  location: string;
  locations:
    readonly StorageLocation[];
  movementType: string;
  period: string;
  onActorChange:
    (value: string) => void;
  onEquipmentChange:
    (value: string) => void;
  onLocationChange:
    (value: string) => void;
  onMovementTypeChange:
    (value: string) => void;
  onPeriodChange:
    (value: string) => void;
  onRetry: () => void;
}) {
  return (
    <>
      <div className="history-filters form-surface">
        <label>
          Период
          <Select
            onChange={(event) =>
              onPeriodChange(
                event.target.value,
              )
            }
            value={period}
          >
            {[
              ["7d", "7 дней"],
              ["30d", "30 дней"],
              ["3m", "3 месяца"],
              ["year", "Год"],
              ["all", "Всё время"],
            ].map(([key, label]) => (
              <option
                key={key}
                value={key}
              >
                {label}
              </option>
            ))}
          </Select>
        </label>

        <label>
          Тип движения
          <Select
            onChange={(event) =>
              onMovementTypeChange(
                event.target.value,
              )
            }
            value={movementType}
          >
            <option value="">
              Все типы
            </option>
            {Object.entries(
              movementLabels,
            ).map(([key, label]) => (
              <option
                key={key}
                value={key}
              >
                {label}
              </option>
            ))}
          </Select>
        </label>

        {canReadAll ? (
          <label>
            Сотрудник
            <Select
              onChange={(event) =>
                onActorChange(
                  event.target.value,
                )
              }
              value={actor}
            >
              <option value="">
                Все доступные
              </option>
              {actors.map((item) => (
                <option
                  key={item.id}
                  value={item.id}
                >
                  {item.name}
                </option>
              ))}
            </Select>
          </label>
        ) : null}

        <label>
          Оборудование
          <Select
            onChange={(event) =>
              onEquipmentChange(
                event.target.value,
              )
            }
            value={equipment}
          >
            <option value="">
              Всё оборудование
            </option>

            {categories
              .filter(
                (item) =>
                  item.parent_id === null,
              )
              .map((family) => (
                <optgroup
                  key={family.id}
                  label={
                    family.display_name
                  }
                >
                  <option
                    value={family.key}
                  >
                    {
                      family.display_name
                    } — всё
                  </option>

                  {categories
                    .filter(
                      (item) =>
                        item.parent_id
                        === family.id,
                    )
                    .map((leaf) => (
                      <option
                        key={leaf.id}
                        value={leaf.key}
                      >
                        {
                          leaf.display_name
                        }
                      </option>
                    ))}

                  {
                    family.key
                    === "transceivers"
                      ? (
                          <option value="long-range">
                            Дальние
                          </option>
                        )
                      : null
                  }
                </optgroup>
              ))}
          </Select>
        </label>

        <label>
          Место хранения
          <Select
            onChange={(event) =>
              onLocationChange(
                event.target.value,
              )
            }
            value={location}
          >
            <option value="">
              Все места
            </option>
            {locations.map((item) => (
              <option
                key={item.id}
                value={item.id}
              >
                {item.name}
                {
                  item.status
                  === "ARCHIVED"
                    ? " (архив)"
                    : ""
                }
              </option>
            ))}
          </Select>
        </label>
      </div>

      {hasError ? (
        <p role="alert">
          Не удалось загрузить часть фильтров.{" "}
          <Button onClick={onRetry}>
            Повторить
          </Button>
        </p>
      ) : null}
    </>
  );
}
