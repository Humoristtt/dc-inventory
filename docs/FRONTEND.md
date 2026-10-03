# Frontend

Frontend — React 19 + TypeScript + Vite. Он работает внутри Telegram Mini App и использует тот же web bundle для browser-based тестов.

## 1. Startup

Entry point: `frontend/src/main.tsx`.

Порядок:

1. подключается Inter;
2. начинается preload JS-модуля текущего pathname;
3. создаются общие providers;
4. `TelegramAccessGate` определяет authentication/access;
5. после APPROVED рендерится `App`;
6. route page загружается lazy.

Preload загружает только код. Он не обходит access gate и не получает protected API data.

## 2. Server state

Server state хранится через TanStack React Query.

Общие правила:

- query key должен однозначно описывать server resource/filter state;
- mutation invalidates или точечно обновляет связанные keys;
- transient route state разрешён только как optimistic/preloaded display hint;
- canonical API response остаётся источником истины;
- отдельный Redux-like store для копирования server state не используется.

## 3. Authentication gate

`TelegramAccessGate` сначала вызывает cookie-session endpoint.

Если ответ 401:

1. загружает vendored Telegram Web App SDK;
2. получает verified-by-server initData flow;
3. выполняет Telegram authentication;
4. получает AuthState;
5. для PENDING опрашивает access state;
6. отображает pending/rejected/blocked UI либо приложение.

SDK лежит локально в `frontend/public/vendor/telegram/telegram-web-app.js`; CI проверяет SHA-256 и размер.

## 4. Routing

Canonical route registry находится в `frontend/src/app/appRoutes.ts`. Он задаёт path, lazy loader/component и optional primary-navigation metadata. `App.tsx`, preload logic и `ApplicationShell.tsx` используют один и тот же registry.

Текущие маршруты:

```text
/catalog
/catalog/new
/catalog/items/:itemId
/catalog/items/:itemId/edit
/catalog/:categoryKey
/movements
/procurement
/procurement/new
/procurement/:requestId
/more
/more/locations
/more/users
```

Unknown route перенаправляется на общий `APP_DEFAULT_PATH` (`/catalog`). Active matching, visibility primary navigation и route preload также выводятся из `appRoutes.ts`.

`routeModules.ts` содержит только lazy import functions и не является вторым registry маршрутов. Это закрывает прежний F-02 maintainability finding.

## 5. Telegram navigation

`useTelegramNavigation`:

- скрывает Telegram BackButton на `/catalog`;
- на внутреннем route показывает BackButton;
- если history entry существует — `navigate(-1)`;
- если приложение открыто непосредственно на deep link — replace на `/catalog`.

SDK может появиться после mount; hook подписан на его состояние.

## 6. Route loading/error boundary

`RouteContent` объединяет:

- Suspense fallback для lazy chunk;
- Error Boundary для chunk/render failure;
- reset ошибки при изменении pathname.

Chunk failure не должен приводить к пустому экрану: пользователь получает явную кнопку reload.

## 7. Capability UX

Page/components скрывают недоступные действия и могут redirect пользователя без capability.

Это только UX. Backend повторно проверяет access status и capability.

Особенно важно не переносить server authorization в route metadata так, чтобы page/backend guards исчезли.

## 8. Design system

Основные tokens: `frontend/src/app/styles/tokens.css`.

Шрифт: Inter Variable / Inter.

Базовые brand colors текущего приложения:

- black `#000000`;
- primary orange `#FEAA13`;
- soft yellow `#F9EB6E`;
- deep gold `#D69303`;
- red `#FF0000`;
- wine `#A1021B`.

Shared primitives находятся в `frontend/src/shared/ui`:

- `PageHeader`;
- `.button` variants;
- `.icon-button`;
- `.section-kicker`;
- `.form-surface`;
- shared responsive rules.

Feature CSS отвечает за layout конкретной страницы, но не должен переопределять base geometry общих controls.

`frontend/scripts/check-design-system.mjs` ловит возврат legacy page headers, shared selectors в feature CSS и другие нарушения ownership.

## 9. Brand assets

Компонент `SpikatelBrand` использует:

- `/brand/spikatel-logo-black.svg`;
- `/brand/spikatel-logo-white.svg`.

Logo растягивается пропорционально через width + auto height. В приложении приоритетен читаемый monochrome вариант.

## 10. Safe area и fullscreen

CSS объединяет:

- browser `env(safe-area-inset-*)`;
- Telegram safe area variables;
- app-updated safe area variables.

Telegram WebApp events обновляют safe-area values.

Desktop-capable Telegram runtime best-effort запрашивает fullscreen. Ошибка requestFullscreen не должна ломать приложение.

Escape guard:

- сначала закрывает верхний dismissible UI;
- затем при Telegram fullscreen пытается выйти из fullscreen;
- не синтезирует повтор пользовательского click.

## 11. Performance contract

Все page routes должны оставаться dynamic entries и не входить в startup graph.

`frontend/scripts/check-bundle.mjs` ограничивает initial JS:

- raw ≤ 310000 bytes;
- gzip ≤ 100000 bytes.

На текущем audited baseline:

```text
initial JS = 287575 bytes
gzip       = 90127 bytes
```

Это CI measurement конкретного baseline, не SLA пользовательской задержки.

## 12. Component boundaries

Прежние крупные orchestration hotspots декомпозированы behavior-preserving change-set:

- `ItemFormPage.tsx` — 434 строки;
- `AdminUsersPage.tsx` — 461;
- `ProcurementDetailPage.tsx` — 430;
- `LineComposer.tsx` — 318;
- `MovementsPage.tsx` — 343;
- `CategoryPage.tsx` — 408.

Вынесенные filters/feed/results/family-grid/catalog-data hooks/components остаются feature-owned. При дальнейшем росте сохраняется тот же принцип: route/page отвечает за orchestration, reusable domain/presentation logic живёт в отдельном owning module.

## 13. Проверки

Минимум после frontend change:

```bash
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

Для затронутого browser flow:

```bash
npm run test:e2e
```

Для реального backend/database path используется isolated full-stack:

```bash
npm run test:e2e:fullstack:local
```

Production runtime дополнительно проверяется GitHub CI.
