import type {
  AttributeDataType,
  CatalogScalar,
  ItemStatus,
} from "../../shared/api/catalog";

function formatDecimalString(
  value: string,
): string {
  const normalized = value.trim();

  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(
    normalized,
  );

  if (!match) {
    return value;
  }

  const sign = match[1] ?? "";
  const integer = match[2] ?? "0";
  const fraction = (
    match[3] ?? ""
  ).replace(/0+$/, "");

  return fraction
    ? `${sign}${integer},${fraction}`
    : `${sign}${integer}`;
}

export function formatAttributeValue(
  value: CatalogScalar,
  unit?: string | null,
  dataType?: AttributeDataType,
): string {
  let formatted: string;

  if (typeof value === "boolean") {
    formatted = value ? "Да" : "Нет";
  } else if (typeof value === "number") {
    formatted = new Intl.NumberFormat(
      "ru-RU",
      {
        maximumFractionDigits: 6,
      },
    ).format(value);
  } else if (dataType === "DECIMAL") {
    formatted = formatDecimalString(value);
  } else {
    formatted = value;
  }

  return unit
    ? `${formatted} ${unit}`
    : formatted;
}

export function formatCatalogAttributeValue(
  key: string,
  value: CatalogScalar,
  unit?: string | null,
  dataType?: AttributeDataType,
): string {
  const formatted =
    formatAttributeValue(
      value,
      unit,
      dataType,
    );

  if (
    key !== "reach"
    || typeof value !== "string"
  ) {
    return formatted;
  }

  return formatted
    .replace(/\s+\/\s+/g, " · ")
    .replace(/\s*;\s*/g, " · ");
}

export function formatItemStatus(
  status: ItemStatus,
): string {
  return status === "ARCHIVED"
    ? "В архиве"
    : "Активная позиция";
}
