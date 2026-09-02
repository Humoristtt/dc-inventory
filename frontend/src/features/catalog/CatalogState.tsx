import type { ReactNode } from "react";

export function CatalogErrorState({
  title = "Не удалось загрузить данные",
  onRetry,
}: {
  title?: string;
  onRetry: () => void;
}) {
  return (
    <div className="catalog-state catalog-state--error" role="alert">
      <span className="catalog-state__mark" aria-hidden="true">!</span>
      <div>
        <strong>{title}</strong>
        <p>Проверьте соединение и попробуйте ещё раз.</p>
      </div>
      <button className="button button--dark" onClick={onRetry} type="button">
        Повторить
      </button>
    </div>
  );
}

export function CatalogEmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="catalog-state catalog-state--empty">
      <span className="catalog-state__mark" aria-hidden="true">∅</span>
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
      {action}
    </div>
  );
}

export function CatalogListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="catalog-skeleton-list" aria-label="Загрузка оборудования">
      {Array.from({ length: count }, (_, index) => (
        <div className="catalog-skeleton" key={index} aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}
