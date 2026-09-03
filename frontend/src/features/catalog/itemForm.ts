import type {
  CatalogItem,
  CatalogScalar,
  CategoryAttribute,
} from "../../shared/api/catalog";

export type AttributeDraft = Record<string, string | boolean>;

export type AttributeValidationResult = {
  values: Record<string, CatalogScalar>;
  errors: Record<string, string>;
};

const DECIMAL_PATTERN = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/;
const INTEGER_PATTERN = /^[+-]?\d+$/;

type ComparableDecimal = {
  coefficient: bigint;
  scale: number;
};

function decimalParts(value: string): ComparableDecimal | null {
  const trimmed = value.trim();
  if (!DECIMAL_PATTERN.test(trimmed)) {
    return null;
  }
  const negative = trimmed.startsWith("-");
  const unsigned = trimmed.replace(/^[+-]/, "");
  const [integer = "0", fractional = ""] = unsigned.split(".");
  const digits = `${integer || "0"}${fractional}`.replace(/^0+(?=\d)/, "");
  const coefficient = BigInt(digits || "0") * (negative ? -1n : 1n);
  return { coefficient, scale: fractional.length };
}

function compareDecimals(left: string, right: string): number | null {
  const leftParts = decimalParts(left);
  const rightParts = decimalParts(right);
  if (leftParts === null || rightParts === null) {
    return null;
  }
  const scale = Math.max(leftParts.scale, rightParts.scale);
  const leftCoefficient = leftParts.coefficient * 10n ** BigInt(scale - leftParts.scale);
  const rightCoefficient = rightParts.coefficient * 10n ** BigInt(scale - rightParts.scale);
  if (leftCoefficient < rightCoefficient) return -1;
  if (leftCoefficient > rightCoefficient) return 1;
  return 0;
}

function metadataString(
  attribute: CategoryAttribute,
  key: "min" | "max",
): string | null {
  const value = attribute.validation_metadata?.[key];
  return typeof value === "number" || typeof value === "string"
    ? String(value)
    : null;
}

function validateBounds(
  attribute: CategoryAttribute,
  rawValue: string,
): string | null {
  const minimum = metadataString(attribute, "min");
  const maximum = metadataString(attribute, "max");
  if (minimum !== null && compareDecimals(rawValue, minimum) === -1) {
    return `Минимальное значение: ${minimum}${attribute.unit ? ` ${attribute.unit}` : ""}`;
  }
  if (maximum !== null && compareDecimals(rawValue, maximum) === 1) {
    return `Максимальное значение: ${maximum}${attribute.unit ? ` ${attribute.unit}` : ""}`;
  }
  return null;
}

export function draftAttributesFromItem(item: CatalogItem): AttributeDraft {
  return Object.fromEntries(
    Object.entries(item.attributes).map(([key, value]) => [
      key,
      typeof value === "boolean" ? value : String(value),
    ]),
  );
}

export function validateDraftAttributes(
  definitions: CategoryAttribute[],
  draft: AttributeDraft,
): AttributeValidationResult {
  const values: Record<string, CatalogScalar> = {};
  const errors: Record<string, string> = {};

  for (const attribute of definitions) {
    const raw = draft[attribute.key];
    if (attribute.data_type === "BOOLEAN") {
      if (typeof raw === "boolean") {
        values[attribute.key] = raw;
      } else if (attribute.required) {
        errors[attribute.key] = "Укажите значение";
      }
      continue;
    }

    const text = typeof raw === "string" ? raw : "";
    const trimmed = text.trim();
    if (trimmed === "") {
      if (attribute.required) {
        errors[attribute.key] = "Обязательное поле";
      }
      continue;
    }

    const maxLength = attribute.validation_metadata?.max_length;
    if (typeof maxLength === "number" && text.length > maxLength) {
      errors[attribute.key] = `Не более ${maxLength} символов`;
      continue;
    }

    if (attribute.data_type === "ENUM") {
      if (!(attribute.allowed_values ?? []).includes(trimmed)) {
        errors[attribute.key] = "Выберите значение из списка";
      } else {
        values[attribute.key] = trimmed;
      }
      continue;
    }

    if (attribute.data_type === "INTEGER") {
      if (!INTEGER_PATTERN.test(trimmed)) {
        errors[attribute.key] = "Введите целое число";
        continue;
      }
      const integer = BigInt(trimmed);
      if (
        integer < BigInt(Number.MIN_SAFE_INTEGER)
        || integer > BigInt(Number.MAX_SAFE_INTEGER)
      ) {
        errors[attribute.key] = "Число слишком велико для безопасной отправки";
        continue;
      }
      const boundsError = validateBounds(attribute, trimmed);
      if (boundsError !== null) {
        errors[attribute.key] = boundsError;
      } else {
        values[attribute.key] = Number(integer);
      }
      continue;
    }

    if (attribute.data_type === "DECIMAL") {
      if (!DECIMAL_PATTERN.test(trimmed)) {
        errors[attribute.key] = "Введите точное десятичное число через точку";
        continue;
      }
      const boundsError = validateBounds(attribute, trimmed);
      if (boundsError !== null) {
        errors[attribute.key] = boundsError;
      } else {
        values[attribute.key] = trimmed;
      }
      continue;
    }

    values[attribute.key] = text;
  }

  return { values, errors };
}

export function attributesEqual(
  left: Record<string, CatalogScalar>,
  right: Record<string, CatalogScalar>,
): boolean {
  const leftEntries = Object.entries(left).sort(([leftKey], [rightKey]) =>
    leftKey.localeCompare(rightKey),
  );
  const rightEntries = Object.entries(right).sort(([leftKey], [rightKey]) =>
    leftKey.localeCompare(rightKey),
  );
  return JSON.stringify(leftEntries) === JSON.stringify(rightEntries);
}
