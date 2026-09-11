import type {
  ReactNode,
} from "react";

import {
  SpikatelBrand,
} from "../brand/SpikatelBrand";
import {
  TelegramFullscreenButton,
} from "../telegram/TelegramFullscreenButton";

export type PageHeaderProps = {
  actions?: ReactNode;
  backLabel?: string;
  children?: ReactNode;
  description?: ReactNode;
  kicker: ReactNode;
  onBack?: () => void;
  title: ReactNode;
};

export function PageHeader({
  actions,
  backLabel = "Назад",
  children,
  description,
  kicker,
  onBack,
  title,
}: PageHeaderProps) {
  return (
    <header className="ds-page-header">
      <div className="ds-page-header__toolbar">
        <SpikatelBrand
          inverse
          title="Инвентаризация ЦОД"
        />

        <TelegramFullscreenButton />
      </div>

      <div className="ds-page-header__heading-row">
        {onBack ? (
          <button
            aria-label={backLabel}
            className="icon-button icon-button--light ds-page-header__back"
            onClick={onBack}
            type="button"
          >
            ←
          </button>
        ) : null}

        <div className="ds-page-header__title">
          <span className="section-kicker">
            {kicker}
          </span>

          <h1>{title}</h1>

          {description ? (
            <div className="ds-page-header__description">
              {description}
            </div>
          ) : null}
        </div>

        {actions ? (
          <div className="ds-page-header__actions">
            {actions}
          </div>
        ) : null}
      </div>

      {children ? (
        <div className="ds-page-header__content">
          {children}
        </div>
      ) : null}
    </header>
  );
}
