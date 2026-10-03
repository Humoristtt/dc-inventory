import {
  useEffect,
  useId,
  useRef,
  type ReactNode,
} from "react";

import {
  Button,
} from "../../shared/ui";

export function ProcurementDialog({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const titleId = useId();
  const dialogRef =
    useRef<HTMLElement>(null);
  const onCloseRef =
    useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const previousFocus =
      document.activeElement
        instanceof HTMLElement
        ? document.activeElement
        : null;
    const dialogElement =
      dialogRef.current;
    const focusableSelector =
      'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

    const firstFocusable =
      dialogElement
        ?.querySelector<HTMLElement>(
          focusableSelector,
        );

    if (firstFocusable) {
      firstFocusable.focus();
    } else {
      dialogElement?.focus();
    }

    const handleKeyDown = (
      event: KeyboardEvent,
    ) => {
      if (
        event.key === "Escape"
      ) {
        event.preventDefault();
        onCloseRef.current();
        return;
      }

      if (
        event.key !== "Tab"
        || !dialogElement
      ) {
        return;
      }

      const focusables =
        Array.from(
          dialogElement
            .querySelectorAll<HTMLElement>(
              focusableSelector,
            ),
        );
      const first =
        focusables[0];
      const last =
        focusables.at(-1);

      if (!first || !last) {
        event.preventDefault();
        dialogElement.focus();
        return;
      }

      if (
        !dialogElement
          .contains(
            document.activeElement,
          )
      ) {
        event.preventDefault();
        first.focus();
        return;
      }

      if (
        event.shiftKey
        && document.activeElement
          === first
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey
        && document.activeElement
          === last
      ) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener(
      "keydown",
      handleKeyDown,
    );

    return () => {
      window.removeEventListener(
        "keydown",
        handleKeyDown,
      );
      previousFocus?.focus();
    };
  }, [open]);

  if (!open) {
    return null;
  }

  return (
    <div
      className="procurement-dialog-backdrop"
      onMouseDown={onClose}
      role="presentation"
    >
      <section
        aria-labelledby={titleId}
        aria-modal="true"
        className="procurement-dialog form-surface"
        onMouseDown={(event) =>
          event.stopPropagation()
        }
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <div className="procurement-dialog__heading">
          <h2 id={titleId}>
            {title}
          </h2>

          <Button
            aria-label="Закрыть"
            className="icon-button"
            onClick={onClose}
          >
            ×
          </Button>
        </div>

        {children}
      </section>
    </div>
  );
}
