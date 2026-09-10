import {
  Component,
  Suspense,
  type ReactNode,
} from "react";

type RouteContentProps = {
  children: ReactNode;
  resetKey?: string;
};

type RouteContentState = {
  failed: boolean;
  resetKey?: string;
};

export class RouteContent extends Component<
  RouteContentProps,
  RouteContentState
> {
  state: RouteContentState = {
    failed: false,
    resetKey: this.props.resetKey,
  };

  static getDerivedStateFromError(): Partial<RouteContentState> {
    return { failed: true };
  }

  static getDerivedStateFromProps(
    props: RouteContentProps,
    state: RouteContentState,
  ): Partial<RouteContentState> | null {
    if (props.resetKey === state.resetKey) {
      return null;
    }

    return {
      failed: false,
      resetKey: props.resetKey,
    };
  }

  render() {
    if (this.state.failed) {
      return (
        <main className="route-status" role="alert">
          <h1>Не удалось открыть страницу</h1>
          <p>Проверьте соединение и загрузите приложение заново.</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
          >
            Обновить приложение
          </button>
        </main>
      );
    }

    return (
      <Suspense
        fallback={
          <main className="route-status" role="status">
            Загружаем страницу…
          </main>
        }
      >
        {this.props.children}
      </Suspense>
    );
  }
}
