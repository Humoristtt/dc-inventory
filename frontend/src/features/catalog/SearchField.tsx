type SearchFieldProps = {
  value: string;
  onChange: (value: string) => void;
  onClear: () => void;
  label: string;
  placeholder: string;
  busy?: boolean;
};

export function SearchField({
  value,
  onChange,
  onClear,
  label,
  placeholder,
  busy = false,
}: SearchFieldProps) {
  return (
    <label className="search-field">
      <span className="visually-hidden">{label}</span>
      <span className="search-field__icon" aria-hidden="true">⌕</span>
      <input
        aria-label={label}
        autoCapitalize="none"
        autoComplete="off"
        autoCorrect="off"
        enterKeyHint="search"
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        type="search"
        value={value}
      />
      {busy ? (
        <span className="search-field__progress" aria-label="Идёт поиск" />
      ) : null}
      {value === "" ? null : (
        <button
          aria-label="Очистить поиск"
          className="search-field__clear"
          onClick={onClear}
          type="button"
        >
          ×
        </button>
      )}
    </label>
  );
}
