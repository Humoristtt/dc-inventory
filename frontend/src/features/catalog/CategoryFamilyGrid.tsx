import {
  Link,
} from "react-router-dom";

import type {
  CategorySummary,
} from "../../shared/api/catalog";

export function CategoryFamilyGrid({
  categoryKey,
  children,
}: {
  categoryKey: string;
  children:
    readonly CategorySummary[];
}) {
  return (
    <div className="category-grid">
      {children.map((child) => (
        <Link
          className="category-tile"
          key={child.id}
          to={
            `/catalog/${child.key}`
          }
        >
          <strong>
            {child.display_name}
          </strong>

          {child.description ? (
            <p>{child.description}</p>
          ) : null}

          <i aria-hidden="true">
            ↗
          </i>
        </Link>
      ))}

      {categoryKey === "transceivers" ? (
        <>
          <Link
            className="category-tile"
            to="/catalog/transceiver_ethernet?rj45=true"
          >
            <strong>RJ-45 SFP</strong>
            <p>
              Медные SFP/SFP+ трансиверы
              с разъёмом RJ-45.
            </p>
            <i aria-hidden="true">
              ↗
            </i>
          </Link>

          <Link
            className="category-tile"
            to="/catalog/transceivers?long_range=true"
          >
            <strong>Дальние</strong>
            <p>Дальность от 2 км.</p>
            <i aria-hidden="true">
              ↗
            </i>
          </Link>
        </>
      ) : null}
    </div>
  );
}
