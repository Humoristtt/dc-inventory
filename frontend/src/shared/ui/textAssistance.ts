/**
 * Browser-level hints that suppress spell-check, autocomplete, autocorrect
 * and automatic capitalization for free-text controls.
 *
 * A mobile operating system may still render its own keyboard UI; the app
 * never opts into predictive text assistance.
 */
export const TEXT_ASSISTANCE_DISABLED = {
  autoCapitalize: "none",
  autoComplete: "off",
  autoCorrect: "off",
  spellCheck: false,
} as const;
