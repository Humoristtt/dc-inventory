import {
  forwardRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

function classNames(
  ...values: Array<string | false | null | undefined>
): string {
  return values.filter(Boolean).join(" ");
}

/**
 * Browser-level hints that suppress spell-check, autocomplete, autocorrect
 * and automatic capitalization for free-text controls.
 *
 * Mobile operating systems may still expose their own keyboard UI, but the
 * application never opts into predictive assistance.
 */
export const TEXT_ASSISTANCE_DISABLED = {
  autoCapitalize: "none",
  autoComplete: "off",
  autoCorrect: "off",
  spellCheck: false,
} as const;

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      className,
      type,
      ...props
    },
    ref,
  ) {
    return (
      <button
        {...props}
        className={classNames(
          "ds-button",
          className?.trim() || "button",
        )}
        ref={ref}
        type={type ?? "button"}
      />
    );
  },
);

export type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  appearance?: "standard" | "bare";
};

export const Input = forwardRef<HTMLInputElement, InputProps>(
  function Input(
    {
      appearance = "standard",
      autoCapitalize: _autoCapitalize,
      autoComplete: _autoComplete,
      autoCorrect: _autoCorrect,
      className,
      spellCheck: _spellCheck,
      type = "text",
      ...props
    },
    ref,
  ) {
    const choiceControl =
      type === "checkbox" || type === "radio";

    return (
      <input
        {...props}
        {...TEXT_ASSISTANCE_DISABLED}
        className={classNames(
          !choiceControl
            && appearance === "standard"
            && "ds-control ds-input",
          className,
        )}
        ref={ref}
        type={type}
      />
    );
  },
);

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement>;

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  function Select(
    {
      className,
      ...props
    },
    ref,
  ) {
    return (
      <select
        {...props}
        className={classNames(
          "ds-control ds-select",
          className,
        )}
        ref={ref}
      />
    );
  },
);

export type TextareaProps =
  TextareaHTMLAttributes<HTMLTextAreaElement>;

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaProps
>(
  function Textarea(
    {
      autoCapitalize: _autoCapitalize,
      autoComplete: _autoComplete,
      autoCorrect: _autoCorrect,
      className,
      spellCheck: _spellCheck,
      ...props
    },
    ref,
  ) {
    return (
      <textarea
        {...props}
        {...TEXT_ASSISTANCE_DISABLED}
        className={classNames(
          "ds-control ds-textarea",
          className,
        )}
        ref={ref}
      />
    );
  },
);
