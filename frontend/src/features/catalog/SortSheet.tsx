import {
  sortOptions,
  type SortSelection,
} from "./catalogSort";

type SortSheetProps = {
  active: SortSelection;
  onSelect: (selection: SortSelection) => void;
  onCancel: () => void;
};

export function SortSheet({ active, onSelect, onCancel }: SortSheetProps) {
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
          <button
            aria-label="Закрыть сортировку"
            className="icon-button"
            onClick={onCancel}
            type="button"
          >
            ×
          </button>
        </header>
        <div className="sort-options">
          {sortOptions.map((option) => {
            const selected = option.sort === active.sort && option.order === active.order;
            return (
              <button
                aria-pressed={selected}
                className={selected ? "sort-option sort-option--active" : "sort-option"}
                key={`${option.sort}:${option.order}`}
                onClick={() => onSelect(option)}
                type="button"
              >
                <span>{option.label}</span>
                <small>{option.hint}</small>
                <i aria-hidden="true">{selected ? "●" : "○"}</i>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
