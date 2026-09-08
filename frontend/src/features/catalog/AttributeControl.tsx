import type { CategoryAttribute } from "../../shared/api/catalog";
import {
  SuggestionInput,
  type SuggestionOption,
} from "./SuggestionInput";

type AttributeControlProps = {
  attribute: CategoryAttribute;
  error: string | undefined;
  onChange: (value: string | boolean | undefined) => void;
  suggestions?: readonly string[];
  suggestionsLoading?: boolean;
  value: string | boolean | undefined;
};

export function AttributeControl({
  attribute,
  error,
  onChange,
  suggestions = [],
  suggestionsLoading = false,
  value,
}: AttributeControlProps) {
  const controlId = `attribute-${attribute.key}`;
  const errorId = `${controlId}-error`;
  const maxLength = attribute.validation_metadata?.max_length;

  // TEXT is single-line by default.
  // Multiline is only an explicit schema decision.
  const multiline = attribute.data_type === "TEXT"
    && attribute.validation_metadata?.preserve_whitespace === true;

  const label = (
    <span className="catalog-form__label">
      {attribute.label}
      {attribute.required ? (
        <b aria-hidden="true">*</b>
      ) : null}
      {attribute.unit ? <small>{attribute.unit}</small> : null}
    </span>
  );

  if (attribute.data_type === "BOOLEAN") {
    const specified = typeof value === "boolean";

    return (
      <div className="catalog-form__field catalog-form__field--boolean">
        {label}

        <div className="catalog-form__boolean-row">
          <label className="catalog-switch" htmlFor={controlId}>
            <input
              aria-describedby={error ? errorId : undefined}
              checked={value === true}
              id={controlId}
              onChange={(event) => onChange(event.target.checked)}
              type="checkbox"
            />
            <span aria-hidden="true" />
            <strong>
              {specified
                ? (value ? "Да" : "Нет")
                : "Не указано"}
            </strong>
          </label>

          {specified && !attribute.required ? (
            <button
              className="text-button"
              onClick={() => onChange(undefined)}
              type="button"
            >
              Сбросить
            </button>
          ) : null}
        </div>

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

  if (attribute.data_type === "ENUM") {
    return (
      <label className="catalog-form__field" htmlFor={controlId}>
        {label}

        <select
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error !== undefined}
          id={controlId}
          onChange={(event) => onChange(event.target.value)}
          value={typeof value === "string" ? value : ""}
        >
          <option value="">Не указано</option>
          {(attribute.allowed_values ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>

        {error ? (
          <small
            className="catalog-form__error"
            id={errorId}
          >
            {error}
          </small>
        ) : null}
      </label>
    );
  }

  const inputMode = attribute.data_type === "INTEGER"
    ? "numeric"
    : attribute.data_type === "DECIMAL"
      ? "decimal"
      : "text";

  const inputValue = typeof value === "string" ? value : "";

  if (multiline) {
    return (
      <label className="catalog-form__field" htmlFor={controlId}>
        {label}

        <textarea
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error !== undefined}
          autoCapitalize="none"
          autoComplete="off"
          autoCorrect="off"
          id={controlId}
          maxLength={
            typeof maxLength === "number"
              ? maxLength
              : undefined
          }
          onChange={(event) => onChange(event.target.value)}
          rows={3}
          spellCheck={false}
          value={inputValue}
        />

        {error ? (
          <small
            className="catalog-form__error"
            id={errorId}
          >
            {error}
          </small>
        ) : null}
      </label>
    );
  }

  const options: SuggestionOption[] = suggestions.map(
    (suggestion) => ({
      key: suggestion,
      label: suggestion,
    }),
  );

  return (
    <SuggestionInput
      error={error}
      id={controlId}
      inputMode={inputMode}
      label={label}
      loading={suggestionsLoading}
      maxLength={
        typeof maxLength === "number"
          ? maxLength
          : undefined
      }
      onChange={(next) => onChange(next)}
      options={options}
      required={attribute.required}
      value={inputValue}
    />
  );
}
