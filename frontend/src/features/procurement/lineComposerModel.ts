import type {
  ProcurementLineInput,
} from "../../shared/api/procurement";

export const MAX_PROCUREMENT_LINES = 500;

export function quantity(
  value: string,
): number | null {
  if (!/^\d+$/.test(value)) {
    return null;
  }

  const parsed = Number(value);

  return (
    Number.isSafeInteger(parsed)
    && parsed > 0
  )
    ? parsed
    : null;
}

export function lineLabel(
  line: ProcurementLineInput,
): string {
  if (
    line.line_type
    === "EXISTING_ITEM"
  ) {
    return (
      line.display_name
      ?? `Карточка ${line.item_id}`
    );
  }

  return [
    line.name,
    line.model,
  ]
    .filter(Boolean)
    .join(" · ");
}
