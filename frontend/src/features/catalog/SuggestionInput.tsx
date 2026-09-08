import {
  useId,
  useState,
  type ReactNode,
} from "react";

export type SuggestionOption = {
  key: string;
  label: string;
  secondary?: string;
};

type SuggestionInputProps = {
  className?: string;
  error?: string;
  id?: string;
  inputMode?: "decimal" | "numeric" | "text";
  label: ReactNode;
  loading?: boolean;
  maxLength?: number;
  onChange: (value: string) => void;
  onSelect?: (option: SuggestionOption) => void;
  options?: readonly SuggestionOption[];
  required?: boolean;
  value: string;
};

export function SuggestionInput({
  className = "",
  error,
  id,
  inputMode = "text",
  label,
  loading = false,
  maxLength,
  onChange,
  onSelect,
  options = [],
  required = false,
  value,
}: SuggestionInputProps) {
  const generatedId = useId();
  const controlId = id ?? `suggestion-${generatedId}`;
  const listboxId = `${controlId}-suggestions`;
  const errorId = `${controlId}-error`;
  const [focused, setFocused] = useState(false);

  const needle = value.trim().toLocaleLowerCase("ru-RU");

  const visibleOptions = needle
    ? [...options]
        .filter((option) =>
          option.label
            .toLocaleLowerCase("ru-RU")
            .includes(needle),
        )
        .sort((left, right) => {
          const leftLabel =
            left.label.toLocaleLowerCase("ru-RU");
          const rightLabel =
            right.label.toLocaleLowerCase("ru-RU");

          const leftPrefix =
            leftLabel.startsWith(needle) ? 0 : 1;
          const rightPrefix =
            rightLabel.startsWith(needle) ? 0 : 1;

          if (leftPrefix !== rightPrefix) {
            return leftPrefix - rightPrefix;
          }

          return left.label.localeCompare(
            right.label,
            "ru",
          );
        })
        .slice(0, 8)
    : [];

  const showSuggestions = focused
    && needle.length > 0
    && (loading || visibleOptions.length > 0);

  function select(option: SuggestionOption) {
    if (onSelect) {
      onSelect(option);
    } else {
      onChange(option.label);
    }
    setFocused(false);
  }

  return (
    <div className={`catalog-form__field smart-suggest ${className}`.trim()}>
      <label htmlFor={controlId}>{label}</label>

      <input
        aria-autocomplete="list"
        aria-controls={showSuggestions ? listboxId : undefined}
        aria-describedby={error ? errorId : undefined}
        aria-expanded={showSuggestions}
        aria-invalid={error !== undefined}
        autoCapitalize="none"
        autoComplete="off"
        autoCorrect="off"
        id={controlId}
        inputMode={inputMode}
        maxLength={maxLength}
        onBlur={() => setFocused(false)}
        onChange={(event) => onChange(event.target.value)}
        onFocus={() => setFocused(true)}
        required={required}
        role="combobox"
        spellCheck={false}
        type="text"
        value={value}
      />

      {showSuggestions ? (
        <div
          className="smart-suggest__menu"
          id={listboxId}
          role="listbox"
        >
          {loading ? (
            <span className="smart-suggest__loading">
              Ищем совпадения…
            </span>
          ) : (
            visibleOptions.map((option) => (
              <button
                className="smart-suggest__option"
                key={option.key}
                onClick={() => select(option)}
                onMouseDown={(event) => event.preventDefault()}
                role="option"
                type="button"
              >
                <strong>{option.label}</strong>
                {option.secondary ? (
                  <small>{option.secondary}</small>
                ) : null}
              </button>
            ))
          )}
        </div>
      ) : null}

      {error ? (
        <small
          className="catalog-form__error"
          id={errorId}
        >
          {error}
        </small>
      ) : null}
    </div>
  );
}
