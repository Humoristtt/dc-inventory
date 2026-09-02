import type { ItemSort, SortOrder } from "../../shared/api/catalog";

export type SortSelection = {
  sort: ItemSort;
  order: SortOrder;
};

export const sortOptions: Array<SortSelection & { label: string; hint: string }> = [
  { sort: "name", order: "asc", label: "По названию", hint: "А → Я" },
  { sort: "name", order: "desc", label: "По названию", hint: "Я → А" },
  { sort: "manufacturer", order: "asc", label: "По производителю", hint: "А → Я" },
  { sort: "available", order: "desc", label: "Сначала доступные", hint: "Больше → меньше" },
  { sort: "available", order: "asc", label: "По доступности", hint: "Меньше → больше" },
  { sort: "total", order: "desc", label: "По общему остатку", hint: "Больше → меньше" },
];

export function sortLabel(selection: SortSelection): string {
  return sortOptions.find(
    (option) => option.sort === selection.sort && option.order === selection.order,
  )?.label ?? "Сортировка";
}
