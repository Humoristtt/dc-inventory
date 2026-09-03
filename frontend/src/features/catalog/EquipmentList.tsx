import { useQueries } from "@tanstack/react-query";

import {
  getCatalogCategory,
  type CatalogItemListEntry,
  type CategoryAttribute,
} from "../../shared/api/catalog";
import { EquipmentCard } from "./EquipmentCard";

type EquipmentListProps = {
  items: CatalogItemListEntry[];
  returnTo: string;
  attributes?: CategoryAttribute[];
};

export function EquipmentList({ items, returnTo, attributes }: EquipmentListProps) {
  const categoryKeys = attributes === undefined
    ? [...new Set(items.map((item) => item.category.key))]
    : [];
  const categoryQueries = useQueries({
    queries: categoryKeys.map((categoryKey) => ({
      queryKey: ["catalog", "category", categoryKey],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        getCatalogCategory(categoryKey, signal),
      staleTime: 5 * 60_000,
    })),
  });
  const attributesByCategory = new Map<string, CategoryAttribute[]>();
  categoryKeys.forEach((key, index) => {
    const data = categoryQueries[index]?.data;
    if (data !== undefined) {
      attributesByCategory.set(key, data.attributes);
    }
  });

  return (
    <div className="equipment-list">
      {items.map((item) => (
        <EquipmentCard
          attributes={attributes ?? attributesByCategory.get(item.category.key)}
          item={item}
          key={item.id}
          returnTo={returnTo}
        />
      ))}
    </div>
  );
}
