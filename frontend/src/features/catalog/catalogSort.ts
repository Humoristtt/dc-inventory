import type {
  ItemSort,
  SortOrder,
} from "../../shared/api/catalog";

export type SortSelection = {
  sort: ItemSort;
  order: SortOrder;
};

export type SortOption =
  SortSelection & {
    label: string;
    hint: string;
  };

export const sortOptions: SortOption[] = [
  {
    sort: "name",
    order: "asc",
    label: "По названию",
    hint: "А → Я",
  },
  {
    sort: "name",
    order: "desc",
    label: "По названию",
    hint: "Я → А",
  },
  {
    sort: "manufacturer",
    order: "asc",
    label: "По производителю",
    hint: "А → Я",
  },
  {
    sort: "available",
    order: "desc",
    label: "Сначала доступные",
    hint: "Больше → меньше",
  },
  {
    sort: "available",
    order: "asc",
    label: "По доступности",
    hint: "Меньше → больше",
  },
  {
    sort: "total",
    order: "desc",
    label: "По общему остатку",
    hint: "Больше → меньше",
  },
  {
    sort: "speed",
    order: "desc",
    label: "По скорости",
    hint: "Больше → меньше",
  },
  {
    sort: "speed",
    order: "asc",
    label: "По скорости",
    hint: "Меньше → больше",
  },
];

export type QuickSortOption = {
  sort: ItemSort;
  label: string;
  defaultOrder: SortOrder;
};

const availabilityQuickSort: QuickSortOption = {
  sort: "available",
  label: "Наличие",
  defaultOrder: "desc",
};

const nameQuickSort: QuickSortOption = {
  sort: "name",
  label: "Название",
  defaultOrder: "asc",
};

const speedQuickSort: QuickSortOption = {
  sort: "speed",
  label: "Скорость",
  defaultOrder: "desc",
};

const transceiverSpeedCategoryKeys = new Set([
  "transceivers",
  "sfp",
  "transceiver_ethernet",
  "transceiver_fc",
]);

function supportsSpeedSort(
  categoryKey: string,
  longRange: boolean,
): boolean {
  return (
    longRange
    || transceiverSpeedCategoryKeys.has(
      categoryKey,
    )
  );
}

export function sortOptionsForContext(
  categoryKey: string,
  longRange: boolean,
): SortOption[] {
  return sortOptions.filter(
    (option) =>
      option.sort !== "speed"
      || supportsSpeedSort(
        categoryKey,
        longRange,
      ),
  );
}

export function quickSortOptions(
  categoryKey: string,
  longRange: boolean,
): QuickSortOption[] {
  return [
    availabilityQuickSort,
    supportsSpeedSort(
      categoryKey,
      longRange,
    )
      ? speedQuickSort
      : nameQuickSort,
  ];
}

export function nextQuickSort(
  current: SortSelection,
  option: QuickSortOption,
): SortSelection {
  if (current.sort !== option.sort) {
    return {
      sort: option.sort,
      order: option.defaultOrder,
    };
  }

  return {
    sort: option.sort,
    order: current.order === "asc"
      ? "desc"
      : "asc",
  };
}

const availabilityFirstCategoryKeys = new Set([
  "transceivers",
  "sfp",
  "transceiver_ethernet",
  "transceiver_fc",
]);

export function catalogDefaultSort(
  categoryKey: string,
): SortSelection {
  return availabilityFirstCategoryKeys.has(
    categoryKey,
  )
    ? {
        sort: "available",
        order: "desc",
      }
    : {
        sort: "name",
        order: "asc",
      };
}

export function sortLabel(
  selection: SortSelection,
): string {
  return sortOptions.find(
    (option) =>
      option.sort === selection.sort
      && option.order === selection.order,
  )?.label ?? "Сортировка";
}
