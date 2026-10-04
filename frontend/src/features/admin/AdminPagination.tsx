import {
  Button,
} from "../../shared/ui";

export type PaginationControlsProps = {
  label: string;
  offset: number;
  limit: number;
  total: number;
  previousLabel: string;
  nextLabel: string;
  onPrevious: () => void;
  onNext: () => void;
};

export function PaginationControls({
  label,
  offset,
  limit,
  total,
  previousLabel,
  nextLabel,
  onPrevious,
  onNext,
}: PaginationControlsProps) {
  const hasPrevious = offset > 0;
  const hasNext =
    offset + limit < total;

  if (!hasPrevious && !hasNext) {
    return null;
  }

  const start =
    total === 0
      ? 0
      : offset + 1;
  const end = Math.min(
    offset + limit,
    total,
  );

  return (
    <div className="admin-pagination">
      <span>
        {label}: {start}–{end} из {total}
      </span>

      <div className="admin-pagination__actions">
        <Button
          className="button button--ghost"
          disabled={!hasPrevious}
          onClick={onPrevious}
        >
          {previousLabel}
        </Button>

        <Button
          className="button button--ghost"
          disabled={!hasNext}
          onClick={onNext}
        >
          {nextLabel}
        </Button>
      </div>
    </div>
  );
}
