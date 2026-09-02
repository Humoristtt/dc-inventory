import { useQuery } from "@tanstack/react-query";

import { getReadyStatus } from "../../shared/api/health";

function RuntimeStatus() {
  const readyQuery = useQuery({
    queryKey: ["runtime", "ready"],
    queryFn: ({ signal }) => getReadyStatus(signal),
    refetchInterval: 30_000,
  });

  if (readyQuery.isPending) {
    return (
      <span className="runtime-status">
        Проверка системы…
      </span>
    );
  }

  if (readyQuery.isError) {
    return (
      <span className="runtime-status runtime-status--error">
        Сервис недоступен
      </span>
    );
  }

  return (
    <span className="runtime-status">
      Система готова
    </span>
  );
}

export function HomePage() {
  return (
    <main className="home">
      <div className="home__glow" aria-hidden="true" />

      <section className="home__content">
        <header className="home__header">
          <span className="home__eyebrow">
            ЦОД · внутренний сервис
          </span>

          <RuntimeStatus />
        </header>

        <div className="home__hero">
          <p className="home__label">
            Инвентаризация оборудования
          </p>

          <h1>Оборудование — под контролем.</h1>

          <p className="home__description">
            Единое место для учёта выдачи, возврата,
            перемещения и фактических остатков оборудования ЦОД.
          </p>
        </div>

        <div className="home__foundation">
          <span className="home__foundation-index">01</span>

          <div>
            <strong>Backend-контур готов</strong>
            <p>
              Каталог и складской учёт реализованы на backend.
              Интерфейс складских операций — следующий продуктовый этап.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
