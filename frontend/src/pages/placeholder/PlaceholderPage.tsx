import { Link } from "react-router-dom";

import { SpikatelBrand } from "../../shared/brand/SpikatelBrand";

type PlaceholderPageProps = {
  eyebrow: string;
  title: string;
  description: string;
};

export function PlaceholderPage({
  eyebrow,
  title,
  description,
}: PlaceholderPageProps) {
  return (
    <main className="placeholder-page">
      <header>
        <SpikatelBrand subtitle="Внутренний каталог ЦОД" />
      </header>
      <section className="placeholder-page__card">
        <span className="section-kicker">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
        <div className="placeholder-page__rule" />
        <span className="placeholder-page__note">
          Раздел появится в следующем продуктовом срезе. Данные не подменяются демонстрационными.
        </span>
        <Link className="button button--dark" to="/catalog">
          Вернуться в каталог
        </Link>
      </section>
    </main>
  );
}
