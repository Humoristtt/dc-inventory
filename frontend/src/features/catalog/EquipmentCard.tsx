import { Link } from "react-router-dom";

import type {
  CatalogItemListEntry,
  CategoryAttribute,
} from "../../shared/api/catalog";
import { formatAttributeValue } from "./format";

type EquipmentCardProps = {
  item: CatalogItemListEntry;
  attributes?: CategoryAttribute[];
  returnTo: string;
};

export function EquipmentCard({
  item,
  attributes = [],
  returnTo,
}: EquipmentCardProps) {
  const visibleAttributes = attributes
    .filter(
      (attribute) =>
        attribute.card_visible && item.attributes[attribute.key] !== undefined,
    )
    .sort((left, right) => left.sort_order - right.sort_order)
    .slice(0, 5);
  const heading = item.model?.trim() || item.name;
  const showName = item.model !== null && item.name.trim() !== heading;

  return (
    <Link
      className="equipment-card"
      state={{ from: returnTo, inventory: item.inventory }}
      to={`/catalog/items/${encodeURIComponent(item.id)}`}
    >
      <div className="equipment-card__visual" aria-hidden="true">
        <span>{item.category.display_name.slice(0, 2).toLocaleUpperCase("ru")}</span>
      </div>

      <div className="equipment-card__content">
        <div className="equipment-card__heading">
          <div className="equipment-card__identity">
            <span className="equipment-card__maker">
              {item.manufacturer?.name ?? "Без производителя"}
            </span>
            <h3>{heading}</h3>
            {showName ? <p>{item.name}</p> : null}
          </div>
          {item.status === "ARCHIVED" ? (
            <span className="status-badge status-badge--archived">Архив</span>
          ) : null}
        </div>

        <div className="equipment-card__meta">
          <span>{item.category.display_name}</span>
          {item.manufacturer_part_number ? (
            <span className="equipment-card__pn">
              PN {item.manufacturer_part_number}
            </span>
          ) : null}
        </div>

        {visibleAttributes.length === 0 ? null : (
          <dl className="attribute-chips">
            {visibleAttributes.map((attribute) => (
              <div key={attribute.key}>
                <dt>{attribute.label}</dt>
                <dd>
                  {formatAttributeValue(
                    item.attributes[attribute.key],
                    attribute.unit,
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}

        <dl className="stock-strip">
          <div className={item.inventory.available_count > 0 ? "stock-strip__available" : "stock-strip__zero"}>
            <dt>Доступно</dt>
            <dd>{item.inventory.available_count}</dd>
          </div>
          <div>
            <dt>У пользователей</dt>
            <dd>{item.inventory.custody_count}</dd>
          </div>
          <div>
            <dt>Всего</dt>
            <dd>{item.inventory.total_count}</dd>
          </div>
        </dl>
      </div>
    </Link>
  );
}
