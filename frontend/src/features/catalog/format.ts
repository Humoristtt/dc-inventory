import type {
  CatalogScalar,
  ItemStatus,
} from "../../shared/api/catalog";

export function formatAttributeValue(
  value: CatalogScalar,
  unit?: string | null,
): string {
  let formatted: string;
  if (typeof value === "boolean") {
    formatted = value ? "Да" : "Нет";
  } else if (typeof value === "number") {
    formatted = new Intl.NumberFormat("ru-RU", {
      maximumFractionDigits: 6,
    }).format(value);
  } else {
    formatted = value;
  }
  return unit ? `${formatted} ${unit}` : formatted;
}

export function formatItemStatus(status: ItemStatus): string {
  return status === "ARCHIVED" ? "В архиве" : "Активная позиция";
}

