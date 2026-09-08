import { Component, Suspense, type ReactNode } from "react";

export class RouteContent extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return <main className="route-status" role="alert">
        <h1>Не удалось открыть страницу</h1>
        <p>Проверьте соединение и загрузите приложение заново.</p>
        <button type="button" onClick={() => window.location.reload()}>Обновить приложение</button>
      </main>;
    }
    return <Suspense fallback={
      <main className="route-status" role="status">Загружаем страницу…</main>
    }>{this.props.children}</Suspense>;
  }
}
