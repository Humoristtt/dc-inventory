# Frontend performance and navigation

Canonical decisions for startup and navigation performance of the
Spikatel Inventory Telegram Mini App.

Last updated: 2026-09-11.

## Scope

This document covers frontend startup, route loading, catalog navigation
and perceived transition latency.

It does not redefine backend authorization, warehouse domain rules,
database semantics or Telegram access policy.

## Security boundary

Frontend role/access state is a presentation and navigation concern.

It is not a security boundary.

Protected backend endpoints continue to validate the server-side
HttpOnly session and the required APPROVED / ADMIN policy for every
request.

The frontend `/api/auth/me` query therefore must not be removed or
replaced by trust in browser state merely to make navigation faster.

The existing periodic APPROVED-session refresh is background work and
is not performed on every catalog route transition.

## Observed pre-optimization critical path

Before the current performance pass, a cold navigation could contain
several serial stages:

1. initial JS;
2. authentication/access gate;
3. lazy route chunk;
4. route-level loading screen;
5. category metadata;
6. item list;
7. item-detail request.

Two concrete avoidable frontend costs were identified:

- `CategoryPage` waited for category-detail success before enabling the
  item-list query;
- opening an item from an already rendered catalog card requested the
  same item payload again before painting the detail page.

The React Query cache is intentionally in-memory. A hard browser/WebView
reload therefore starts with an empty query cache.

## Accepted MVP strategy

The MVP keeps route-level code splitting and the existing bundle-size
contract.

Optimization is performed by moving work earlier and overlapping
independent work rather than by making every route part of the initial
bundle.

### Current-route preload

At application bootstrap the route module matching
`window.location.pathname` starts loading immediately.

This happens in parallel with the startup authentication request.

Downloading route code does not grant access and does not bypass the
Telegram access gate.

### Fixed-route warmup

After an approved application mounts, the small fixed set of route
chunks is warmed in the background.

The routes remain dynamic imports and therefore remain outside the
initial JS import graph.

This trades a small amount of background transfer for predictable
subsequent navigation in the internal warehouse application.

### Stable route boundary

`RouteContent` remains the Suspense/error recovery boundary.

It is no longer remounted purely because `location.pathname` changed.

A route failure is reset when navigation changes the route reset key.

### Catalog family/leaf fast path

The catalog hierarchy response already contains `id`, `key` and
`parent_id`.

When hierarchy data is cached, `CategoryPage` can determine whether the
destination is a family or leaf without waiting for the category-detail
request.

For a leaf, item loading can therefore start while category metadata is
still loading.

When a family page is visible, metadata for that family's small set of
child leaf categories is prefetched. This avoids globally prefetching
every category-detail endpoint.

### Item-detail preview

A catalog list entry already contains the complete catalog item identity,
status and attributes plus an inventory summary.

When navigation originates from an equipment card, that catalog item is
passed as route state and used as React Query placeholder data for the
detail page.

The actual item endpoint still runs and revalidates server state.
Inventory-location breakdown continues to use its own canonical API
queries.

The preview therefore improves first paint without turning client state
into an authority.

## Deliberately rejected MVP complexity

The current MVP does not add:

- Redux or another global state framework;
- service workers;
- IndexedDB query persistence;
- localStorage persistence of protected catalog data;
- SSR;
- a new router;
- a bootstrap/BFF endpoint;
- Redis or another frontend cache service.

Persistent browser caching of authenticated query data is intentionally
avoided for now because it increases stale-data and shared-device /
cross-user lifecycle complexity.

## Performance acceptance

Automated acceptance must prove behavior, not only elapsed wall-clock
time.

The browser suite therefore uses controlled pending network requests to
prove that:

- the current deep-route JS chunk starts loading while startup auth is
  still pending;
- leaf item loading starts while category metadata is deliberately held
  unresolved;
- item detail can paint from list preview while the detail endpoint is
  deliberately held unresolved;
- normal warmed navigation does not require the full-page
  `Загружаем страницу…` fallback.

The normal typecheck, lint, unit, production build/bundle contract and
full Warehouse browser suite remain required.

Final acceptance additionally requires real Telegram mobile/desktop
visual testing after deployment.

## Telegram Desktop fullscreen finding

PR #53 changed desktop fullscreen from automatic to user initiated in
order to isolate the first-click problem.

Real Telegram Desktop testing showed:

- windowed/expanded mode accepted hover and the first click normally;
- after entering Telegram native fullscreen, the first mouse interaction
  was consumed.

PR #54 added best-effort `window.focus()` / DOM focus recovery after
`fullscreenChanged`.

Real Telegram Desktop testing showed no improvement.

PR #55 therefore restored the accepted automatic desktop-fullscreen
behavior.

Production was restored to commit:

    676c5276b6427194bd75e6d8a0d2ffb16bbb8b61

The fullscreen first-input behavior is treated as a Telegram Desktop /
native WebView limitation, not as a React/catalog performance defect.

No further synthetic click or focus-replay workaround is planned for
the MVP.
