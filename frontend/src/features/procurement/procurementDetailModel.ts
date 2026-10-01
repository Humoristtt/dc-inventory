import type {
  ProcurementLine,
  ProcurementLineInput,
} from "../../shared/api/procurement";

export function procurementLineTitle(
  line: ProcurementLine,
): string {
  return [
    line.display_snapshot
      .manufacturer_name,
    line.display_snapshot.name,
    line.display_snapshot.model,
  ]
    .filter(
      (
        value,
      ): value is string =>
        typeof value === "string"
        && Boolean(value),
    )
    .join(" · ");
}

export function procurementInputFromLine(
  line: ProcurementLine,
): ProcurementLineInput {
  if (
    line.line_type
      === "EXISTING_ITEM"
    && line.catalog_item_id
  ) {
    return {
      line_type: "EXISTING_ITEM",
      item_id:
        line.catalog_item_id,
      display_name:
        procurementLineTitle(
          line,
        ),
      quantity: line.quantity,
    };
  }

  const snapshot =
    line.display_snapshot;

  return {
    line_type: "PROPOSED_ITEM",
    category_key:
      String(
        snapshot.category_key
        ?? "",
      ),
    manufacturer_id:
      typeof snapshot
        .manufacturer_id
        === "string"
        ? snapshot
            .manufacturer_id
        : null,
    name:
      String(
        snapshot.name ?? "",
      ),
    model:
      typeof snapshot.model
        === "string"
        ? snapshot.model
        : null,
    attributes: (
      snapshot.attributes ?? {}
    ) as Record<
      string,
      | string
      | number
      | boolean
    >,
    quantity: line.quantity,
  };
}
