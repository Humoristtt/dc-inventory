import type {
  CatalogItemListEntry,
} from "../../shared/api/catalog";

export function normalizeSearch(value: string): string {
  return value
    .normalize("NFKC")
    .toLocaleLowerCase("ru")
    .replaceAll("ё", "е")
    .replace(/[^a-zа-я0-9]+/giu, " ")
    .trim();
}

export function editDistance(left: string, right: string): number {
  if (!left.length) return right.length;
  if (!right.length) return left.length;

  let previous = Array.from(
    { length: right.length + 1 },
    (_, index) => index,
  );

  for (let row = 1; row <= left.length; row += 1) {
    const current = [row];

    for (let column = 1; column <= right.length; column += 1) {
      const substitution =
        previous[column - 1]
        + (left[row - 1] === right[column - 1] ? 0 : 1);

      current[column] = Math.min(
        current[column - 1] + 1,
        previous[column] + 1,
        substitution,
      );
    }

    previous = current;
  }

  return previous[right.length];
}

export function tokenSimilarity(query: string, candidate: string): number {
  if (!query || !candidate) return 0;
  if (candidate === query) return 1;
  if (candidate.startsWith(query)) return 0.96;
  if (candidate.includes(query)) return 0.9;
  if (query.includes(candidate) && candidate.length >= 3) return 0.82;

  const distance = editDistance(query, candidate);
  const longest = Math.max(query.length, candidate.length);
  return longest ? 1 - distance / longest : 0;
}

export function fuzzyScore(item: CatalogItemListEntry, rawQuery: string): number {
  const query = normalizeSearch(rawQuery);
  if (!query) return 1;

  const queryTokens = query.split(" ").filter(Boolean);
  const searchable = normalizeSearch(
    [
      item.category.display_name,
      item.manufacturer?.name,
      item.name,
      item.model,
      ...Object.values(item.attributes).map(String),
    ]
      .filter(Boolean)
      .join(" "),
  );
  const candidateTokens = searchable.split(" ").filter(Boolean);

  if (searchable.includes(query)) return 2;

  const scores = queryTokens.map((queryToken) =>
    Math.max(
      0,
      ...candidateTokens.map((candidateToken) =>
        tokenSimilarity(queryToken, candidateToken),
      ),
    ),
  );

  return scores.reduce((sum, score) => sum + score, 0) / scores.length;
}

export function catalogItemLabel(item: CatalogItemListEntry): string {
  return [
    item.category.display_name,
    item.manufacturer?.name,
    item.name,
    item.model,
  ]
    .filter(Boolean)
    .join(" · ");
}


