import type { CategoryAttribute } from "../../shared/api/catalog";

type AttributeControlProps = {
  attribute: CategoryAttribute;
  error: string | undefined;
  onChange: (value: string | boolean | undefined) => void;
  value: string | boolean | undefined;
};

export function AttributeControl({
  attribute,
  error,
  onChange,
  value,
}: AttributeControlProps) {
  const controlId = `attribute-${attribute.key}`;
  const errorId = `${controlId}-error`;
  const maxLength = attribute.validation_metadata?.max_length;
  const multiline = attribute.data_type === "TEXT"
    && (
      attribute.validation_metadata?.preserve_whitespace === true
      || (typeof maxLength === "number" && maxLength > 255)
    );
  const label = (
    <span className="catalog-form__label">
      {attribute.label}
      {attribute.required ? <b aria-label="обязательное поле">*</b> : null}
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
            <strong>{specified ? (value ? "Да" : "Нет") : "Не указано"}</strong>
          </label>
          {specified && !attribute.required ? (
            <button className="text-button" onClick={() => onChange(undefined)} type="button">
              Сбросить
            </button>
          ) : null}
        </div>
        {error ? <small className="catalog-form__error" id={errorId}>{error}</small> : null}
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
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        {error ? <small className="catalog-form__error" id={errorId}>{error}</small> : null}
      </label>
    );
  }

  const inputMode = attribute.data_type === "INTEGER" ? "numeric" : "decimal";
  const inputValue = typeof value === "string" ? value : "";
  return (
    <label className="catalog-form__field" htmlFor={controlId}>
      {label}
      {multiline ? (
        <textarea
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error !== undefined}
          id={controlId}
          onChange={(event) => onChange(event.target.value)}
          rows={attribute.key === "reach" ? 4 : 2}
          value={inputValue}
        />
      ) : (
        <input
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error !== undefined}
          id={controlId}
          inputMode={attribute.data_type === "TEXT" ? "text" : inputMode}
          onChange={(event) => onChange(event.target.value)}
          type="text"
          value={inputValue}
        />
      )}
      {error ? <small className="catalog-form__error" id={errorId}>{error}</small> : null}
    </label>
  );
}

