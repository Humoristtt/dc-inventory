import type {
  SortOption,
  SortSelection,
} from "./catalogSort";
import {
  Button,
} from "../../shared/ui";

type SortSheetProps = {
  active: SortSelection;
  options: readonly SortOption[];
  onSelect: (selection: SortSelection) => void;
  onCancel: () => void;
};

export function SortSheet({
  active,
  options,
  onSelect,
  onCancel,
}: SortSheetProps) {
  return (
    <div
      className="sheet-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onCancel();
        }
      }}
    >
      <section
        aria-labelledby="sort-sheet-title"
        aria-modal="true"
        className="sheet sort-sheet"
        role="dialog"
      >
        <header className="sheet__header">
          <div>
            <span className="section-kicker">Порядок списка</span>
            <h2 id="sort-sheet-title">Сортировка</h2>
          </div>
          <Button
            aria-label="Закрыть сортировку"
            className="icon-button"
            data-escape-dismiss=""
            onClick={onCancel}
            type="button"
          >
            ×
          </Button>
        </header>
        <div className="sort-options">
          {options.map((option) => {
            const selected = option.sort === active.sort && option.order === active.order;
            return (
              <Button
                aria-pressed={selected}
                className={selected ? "sort-option sort-option--active" : "sort-option"}
                key={`${option.sort}:${option.order}`}
                onClick={() => onSelect(option)}
                type="button"
              >
                <span>{option.label}</span>
                <small>{option.hint}</small>
                <i aria-hidden="true">{selected ? "●" : "○"}</i>
              </Button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
