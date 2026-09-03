# История проекта

Здесь фиксируются ключевые этапы развития проекта, инфраструктурные изменения и архитектурные решения.

## 2026-08-31 — Инициализация проекта

- Создан private-репозиторий `Humoristtt/dc-inventory`.
- Первый commit: `d889f3bcc4a31d9bd8660eb8827afad3e73fffe6`.
- Подготовлена production VM `dc-inventory` на Ubuntu Server 24.04.4 LTS.
- Выделено 4 vCPU, 8 GB RAM, 100 GB disk и 2 GB swap.
- Root filesystem расширен через LVM примерно до 98 GB.
- Настроен SSH только по ключу; password authentication и root login отключены.
- Настроен локальный SSH alias `ssh inventory`.
- Установлены Docker Engine, Docker Compose и containerd из официального Docker repository.
- Для Docker включены `live-restore` и ограничение размера container logs.
- Production VM получила отдельный read-only GitHub Deploy Key `dc-inventory-prod`.
- Проверен доступ к GitHub, Docker Hub и Cloudflare.
- Установлено, что прямое TCP-соединение VM к `api.telegram.org:443` завершается timeout до TLS handshake.
- Принято решение не направлять весь трафик VM через VPN/WARP; Telegram Bot API будет обслуживаться через отдельный безопасный gateway.
- Получены исходные Excel-файлы текущей складской номенклатуры.
- Получены фирменный guidebook Spikatel 2026 и оригинальные web-логотипы.
- Документация проекта ведётся на русском языке и должна обновляться вместе с реализацией.

## 2026-08-31 — Backend runtime foundation

- Создан backend foundation на Python 3.12 и FastAPI.
- Зафиксирован архитектурный стиль модульного монолита.
- Выделены инфраструктурные слои `api`, `core`, `db` и каталог будущих предметных модулей `modules`.
- Настроен SQLAlchemy 2 в async-режиме через `asyncpg`.
- Добавлена обязательная конфигурация `DATABASE_URL`.
- Добавлен ограниченный timeout подключения к PostgreSQL.
- Настроен Alembic в async-режиме.
- Строка подключения к PostgreSQL не хранится в `alembic.ini`.
- Создан baseline Alembic `48c2f07f01a0`.
- Добавлен PostgreSQL 18 для локальной разработки через `compose.dev.yaml`.
- Development PostgreSQL публикуется только на `127.0.0.1:55432`.
- Локальный `.env` исключён из Git; добавлен `.env.example`.
- Реализован `/api/health/live`.
- Реализован `/api/health/ready` с реальной проверкой PostgreSQL.
- DB health logic вынесена из HTTP-слоя в `app/db/health.py`.
- Настроены Ruff, mypy strict и Pytest.
- Unit tests проверяют успешный readiness и ответ HTTP 503 при недоступной БД.
- Выполнен acceptance с реальным PostgreSQL: `UP -> 200/200`, `DOWN -> 200/503`, `BACK -> 200/200`.
- Подтверждено восстановление readiness без рестарта backend.
- Для будущих автоматизированных runtime-проверок вместо фиксированных задержек будет использоваться bounded readiness polling.

## 2026-08-31 — Production-shaped runtime foundation

- Добавлен production Compose `compose.yaml`.
- В production на host публикуется только Nginx на `127.0.0.1:8080`.
- Backend и PostgreSQL не публикуют host-порты.
- Добавлен `requirements-dev.lock` с hash-locked development/CI-зависимостями.
- Добавлен GitHub Actions CI для backend, frontend, миграций и сборки Docker images.
- Удалены остаточные файлы стандартного Vite scaffold.
- Добавлена deployment-документация.

## 2026-08-31 — Архитектурный pre-feature hardening

- Проведён полный аудит runtime foundation перед Telegram authentication и первой предметной миграцией.
- Добавлен naming convention SQLAlchemy до появления предметных constraints.
- Зафиксированы DB pool, statement timeout и lock timeout boundaries.
- PostgreSQL runtime sessions закреплены в UTC.
- Production Swagger/OpenAPI отключены.
- Исправлена proxy-chain семантика Cloudflare -> Nginx -> Uvicorn для scheme и client IP.
- PostgreSQL изолирован от web отдельной internal Docker network.
- CI расширен production-shaped runtime smoke test через Nginx, FastAPI, Alembic и PostgreSQL.
- Обновлена canonical документация frontend/runtime/deployment.

## 2026-09-01 — Telegram identity, auth и access foundation

- `533a7b5` — User / TelegramIdentity / AccessRequest persistence.
- `c13f030` — Telegram initData validation, server-side AuthSession и auth API.
- `93490cd` — frontend auth gate, кликабельный `@Humoristttt`, access request и
  pending flow.
- Post-checkpoint audit выделил Stage 4.3a до outbox/webhook: retry после
  `REJECTED`, backend `Approved`/`Admin` boundary, bootstrap ADMIN consistency,
  PostgreSQL integration tests, Compose secret boundary и синхронизация docs.
- Повторный source audit Stage 4.3a выявил stale access-cache риск во frontend:
  access-state одного пользователя не должен иметь приоритет над свежим auth-state
  и не должен переиспользоваться между user ID.
- Stage 4.3b закрывает user-scoped access cache, PENDING-only frontend authority,
  реальный PostgreSQL race первого Telegram login и CI runtime network boundaries.
- Stage 4.4 начинается после полного gate Stage 4.3b.
## 2026-09-01 — Stage 4.4 — Telegram delivery и production access

- Реализован transactional `NotificationOutbox`.
- Добавлен отдельный `telegram-worker` с PostgreSQL claim/lease,
  `FOR UPDATE SKIP LOCKED`, bounded retry и `PENDING/SENT/DEAD` lifecycle.
- Реализован Telegram webhook с secret-token validation и persistent
  `TelegramUpdate.update_id` dedupe.
- Реализованы opaque ADMIN approve/reject callbacks.
- Решение доступа выполняется только `ADMIN + APPROVED`, транзакционно и
  идемпотентно; terminal user state не может быть переписан stale callback.
- После решения ADMIN inline-кнопки очищаются, пользователь получает
  Telegram-уведомление.
- Развёрнут отдельный Cloudflare Worker Telegram Gateway с gateway secret и
  фиксированным Bot API allowlist.
- Telegram webhook зарегистрирован на
  `https://app.spik-inventory.ru/api/telegram/webhook`.
- Реальный `sendMessage` через Gateway проверен.
- Production `/start` выявил Cloudflare `403 / 1010` для стандартного
  `Python-urllib` User-Agent до выполнения Worker.
- PR #6 добавил явный service User-Agent
  `dc-inventory-telegram-worker/1.0`; PR #7 исправил typing regression test,
  после чего полный CI прошёл успешно.
- Production runtime code обновлён до
  `08aa052d2af3e9c7e9cb9a2bce670cf6674b6c97`.
- Реальный `/start` проходит полный Telegram → webhook → FastAPI → outbox →
  worker → Cloudflare Gateway → Telegram маршрут.
- Production access smoke со вторым Telegram account завершён:
  request access → ADMIN notification → approve → user notification →
  успешный вход в Mini App.
- Production VM после закрытия runtime-этапа имеет чистый worktree, только
  локальную ветку `main` и не содержит untracked project files.
- Stage 4 production MVP завершён.
- Следующий предметный этап — Stage 5 Catalog Foundation.

## 2026-09-01 — Stage 5 — Catalog Foundation

- Добавлен предметный модуль `app/modules/catalog`.
- Реализованы Category, Manufacturer, Item, CategoryAttribute и typed
  ItemAttributeValue.
- Item закреплён как каталожная позиция, отдельная от будущего физического
  InventoryUnit.
- Добавлены QUANTITY/SERIAL defaults и ACTIVE/ARCHIVED lifecycle без публичного
  hard-delete.
- PostgreSQL enforcing включает exactly-one typed value, unique keys,
  normalized manufacturer/internal code и composite cross-category foreign keys.
- Реализована metadata-driven validation TEXT/INTEGER/DECIMAL/BOOLEAN/ENUM,
  required fields, allowed values, exact Decimal и canonical units.
- Добавлены non-destructive duplicate candidates по manufacturer part number
  либо exact normalized name/model.
- Добавлены Approved read API и Admin mutation API с immutable category и
  accounting mode, full-replacement PATCH semantics для attributes и
  idempotent archive/unarchive.
- Alembic revision `f4a5b6c7d8e9` version-controls пять system categories и их
  initial attributes.
- Добавлены focused domain, PostgreSQL 18, API и authorization tests.
- После независимого аудита Stage 5 regression tests отвязаны от глобального
  Alembic head и точного общего числа Category: они проверяют устойчивые
  свойства пяти initial system schemas и допускают будущие migrations/categories.
- DECIMAL validation приведена в точное соответствие `NUMERIC(30,10)`:
  максимум 20 integral и 10 fractional digits до persistence.
- ORM delete Manufacturer передан PostgreSQL `ON DELETE RESTRICT` через
  `passive_deletes="all"`; добавлен real-PostgreSQL regression test.
- Канонический contract зафиксирован в `docs/CATALOG_SCHEMA.md`.
- Source Excel/CSV в текущем workspace отсутствовал; соответствующие
  vocabularies оставлены provisional, production/source reconciliation не
  заявлена выполненной.

## 2026-09-01 — Stage 5 — Source reference refinement

- Проанализированы три локальных reference workbook: шесть sheets и 176
  непустых data rows.
- Зафиксировано продуктовое решение: source spreadsheets используются только
  для catalog design, не являются inventory database/import source; quantities,
  balances и operational state не переносятся.
- Подтверждены Item/Manufacturer/identifier boundaries, typed EAV и
  deterministic duplicate candidates без backend contract changes.
- Recurring RJ45 patch-cord examples выделены в system Category
  `copper_network_cable` с metadata-driven attributes.
- Для кабелей питания добавлены optional conductor count/cross-section fields;
  SFP vocabularies дополнены `XFP` и `SC Simplex`.
- Изменения versioned metadata оформлены новой migration `a6b7c8d9e0f1`;
  историческая `f4a5b6c7d8e9` не изменялась.
- Ambiguous multi-rate/reach/wavelength и disk model/MPN/source formatting
  задокументированы как manual decisions без fuzzy/import logic.
- Refinement merged в `main` через PR #10; migration стала immutable parent для
  Stage 6.

## 2026-09-01 — Stage 6 — Warehouse Core / Inventory Ledger

- Добавлен предметный модуль `app/modules/inventory` с Location, InventoryUnit,
  Movement, MovementLine и StockBalance.
- Каноническая warehouse history закреплена как append-only journal; PostgreSQL
  triggers запрещают UPDATE/DELETE movement headers и lines.
- QUANTITY использует positive integer balances ровно в одной Location/holder
  position с partial unique indexes и transactional projection updates.
- SERIAL использует physical InventoryUnit identities, deterministic normalized
  serial/WWN uniqueness и состояния STORED/ISSUED/WRITTEN_OFF/VOIDED.
- Реализованы RECEIPT, ISSUE, RETURN, TRANSFER, WRITE_OFF, linked CORRECTION и
  one-per-original REVERSAL без generic signed-delta API.
- Actor отделён от physical source/destination holder; history сохраняет display
  snapshots пользователей, Location, Item/manufacturer/model/MPN и serial.
- Movement mutations получили PostgreSQL-backed idempotency по `(actor,
  client_request_id)` и canonical request fingerprint.
- Детерминированные row locks и transaction-scoped advisory locks закрывают
  underflow, duplicate serial activation и multi-process allocation races.
- Добавлены Approved read API и Admin-only mutation API со stable domain errors.
- Migration `b7c8d9e0f1a2` создана поверх immutable `a6b7c8d9e0f1`; opening
  balances, spreadsheet quantities и serial units не импортируются.
- Добавлены focused model, PostgreSQL lifecycle/integrity, API authorization,
  idempotency и real concurrent last-unit/serial allocation tests.
- Канонический contract зафиксирован в `docs/WAREHOUSE_DOMAIN.md`.

## 2026-09-02 — Stage 6 independent-review remediation

- Reversal больше не может вернуть current state в archived Location; после
  explicit ADMIN unarchive тот же reversal снова допустим.
- Archived Item policy разрешает управлять existing QUANTITY/SERIAL inventory
  через return/transfer/write-off/reversal, но запрещает новый receipt/issue и
  external archived correction.
- Non-null normalized WWN стал глобально уникальным, serial uniqueness остался
  Item-scoped; multi-line identity locks и row locks приведены к одному
  детерминированному graph `identity -> InventoryUnit -> Item`.
- Добавлены safe retryable PostgreSQL conflicts для `40P01`/`55P03`/`40001`,
  post-casefold length checks и controlled BIGINT input/addition bounds.
- `MovementLine.line_no` сохраняет request order, `wwn_snapshot` сохраняет
  physical identity history, а snapshot display capacity согласована с полным
  Telegram identity contract.
- Correction link теперь требует original Item и position; correction-to-absent
  SERIAL означает `VOIDED`, а `WRITTEN_OFF` создаёт только WRITE_OFF.
- Datasheet URL ограничен valid http/https semantics; schema regression больше
  не считает `b7` вечным Alembic head.
- Добавлен read-only projection reconciliation SQL/runbook и явный запрет
  production inventory entry до automated PostgreSQL backup и успешного real
  restore test.
- Повторный independent review выявил зависимость history/reconciliation от wall
  clock + UUIDv4; добавлен database-generated `Movement.journal_seq`, который
  теперь задаёт канонический порядок journal даже при rollback clock/NTP.
- Следующий review pass выявил, что UPDATE/DELETE protection не запрещала
  post-commit INSERT дополнительной MovementLine. `Movement.line_count` и
  deferred PostgreSQL constraint triggers теперь запечатывают exact contiguous
  line set на transaction commit и запрещают неполный header.
- Stage 6 остаётся на independent review/CI и не помечен DONE; Stage 7 не начат.

## 2026-09-02 — Stage 6 final audit closeout — local, pending PR

- Создан final-audit branch `audit/stage6-final-review-20260902`.
- Исходный checkpoint:
  `bb76b4b4a12e6986dfdbadc086562a53d1d2ad96`.
- Полный final source audit выполнен.
- Production-blocking P1 findings исправлены и проверены реальными
  least-privilege PostgreSQL roles.
- Backend runtime получил narrow `UPDATE(processed_at)` для
  `telegram_updates`.
- Correction/reversal original context переведён с row locking immutable
  Movement на transaction-scoped advisory lock.
- Runtime sequence access сужен до `movements_journal_seq_seq`.
- Runtime больше не имеет `DELETE` на `auth_sessions`.
- Controlled `DEAD -> PENDING` access notification recovery переиспользует
  существующую callback pair и не даёт backend broad outbox UPDATE.
- Production notification worker требует HTTPS Telegram Gateway URL.
- Same-origin vendored Telegram Web App SDK имеет CI SHA-256 verification и
  отдельные load-error/timeout frontend states.
- Technical retention использует отдельную least-privilege DB identity и
  имеет CI execution proof.
- Full Ruff и strict mypy после remediation проходят.
- Текущий migration head: `c8d9e0f1a2b3`.
- Созданы `docs/PRODUCT_REQUIREMENTS.md` и `docs/OPERATIONS.md`.
- Canonical documentation и ROADMAP синхронизированы.
- Merge/deploy ещё не выполнены.
- Следующий gate:
  final local gate -> commit/push -> Pull Request CI -> merge.

## 2026-09-02 — Stage 6 production close и переход к Stage 7

- Final local gate Stage 6 завершён с `P0=0`, `P1=0`, `P2=0`.
- Final remediation commit: `1c4c803a09e872fdcbc4069e159c486b2bd16ba2`.
- CI harness fixes: `d38417e6d14822c55884cbabebd9cf375f29afc0` и `3c882d56d8d8065c1c885c2694fc1ced9d3f135b`.
- PR #11 прошёл четыре required checks: backend, frontend, runtime и telegram-gateway.
- PR #11 merged в `main`; production source SHA: `7e04c8da72d3b12bd78184f323a984ea6a86618c`.
- Production PostgreSQL upgraded с `e8f1a2b3c4d5` до `c8d9e0f1a2b3`.
- Runtime работает с отдельными least-privilege DB identities для backend, Telegram worker и maintenance worker.
- Technical retention production iteration PASS.
- Host публикует только `127.0.0.1:8080`; backend/PostgreSQL host ports отсутствуют; DB network internal.
- Projection reconciliation завершён с zero QUANTITY drift и zero SERIAL drift.
- Public Cloudflare health/live/ready PASS.
- Реальный Telegram `/start` production smoke PASS.
- Local и remote Stage 6 branches удалены; source приведён к `main`.
- `main` защищён: PR required, strict required CI, admin enforcement, force-push/delete запрещены.
- Automated off-VM PostgreSQL backup и real restore test сознательно отложены. До их выполнения запрещён только ввод настоящих канонических складских остатков; product development продолжается на synthetic/test data.
- Текущий продуктовый этап: Stage 7 — Catalog Read API / Search / Filters.

## 2026-09-02 — Stage 7 Catalog Read API — local implementation

- `GET /api/catalog/items` получил tokenized global/category search,
  manufacturer/location/availability filters, metadata-driven exact/range
  filters, deterministic sorting/pagination и set-based inventory summary.
- Serial/WWN identity search возвращает parent Item для всех lifecycle states;
  WRITTEN_OFF/VOIDED не входят в current totals.
- Добавлен `GET /api/catalog/items/facets` с common/dynamic facets, real range
  bounds и self-excluding counts.
- Все шесть versioned categories проходят один generic query path; category
  branches в production code не добавлены.
- Migration `d9e0f1a2b3c4` добавляет `pg_trgm` и Stage 7 search/typed EAV/current
  inventory indexes поверх `c8d9e0f1a2b3`.
- Реальные inventory data не вводились; backup/restore gate остаётся deferred до
  canonical inventory entry.
- Статус: implemented locally; focused review, PR CI и production deploy pending.

## 2026-09-03 — Stage 7 production close и переход к Stage 8

- Focused review Stage 7 закрыт без P0/P1/P2 findings; повторная реализация Stage 7 не потребовалась.
- PR #13 `Stage 7: catalog search, filters and facets` прошёл четыре required checks:
  backend, frontend, runtime и telegram-gateway.
- PR #13 merged в `main`; production source SHA:
  `50d013feb04d13d0976fc196ced99b589a95af6b`.
- Перед миграцией создан локальный rollback checkpoint
  `/home/install/.dc-inventory-db-backups/pre-stage7-50d013f.dump`,
  размер 92K, SHA-256
  `516f8647bfd173b87f7ecf845ebff0c9ddb432ad52d8438a90cd11ff4dbb1952`;
  artifact успешно читается `pg_restore --list`.
- Production PostgreSQL upgraded с `c8d9e0f1a2b3` до `d9e0f1a2b3c4`.
- DB least-privilege permissions повторно применены после migration.
- Backend, Telegram worker и maintenance worker пересозданы на Stage 7 backend image.
- Production runtime после deploy: backend healthy, PostgreSQL healthy, web healthy,
  Telegram worker и maintenance worker running.
- Local Nginx health/live/ready PASS.
- Public Cloudflare HTTPS health/live/ready PASS.
- `GET /api/catalog/items` и `GET /api/catalog/items/facets` в production
  подтверждены через существующую authorization boundary: без session возвращают
  `401 authentication required`, а не `404/500`.
- Реальные canonical inventory data не вводились; automated off-VM backup +
  verified real restore остаются обязательным Stage 15 production-data gate.
- Stage 7 завершён. Текущий продуктовый этап — Stage 8 Working Mini App UX.

## 2026-09-03 — Stage 8A Working Mini App Catalog UX

- Runtime hero заменён рабочим mobile-first shell с постоянной нижней навигацией
  и осмысленными placeholder-состояниями для ещё не реализованных разделов.
- Catalog landing, global search, generic category list и Item detail используют
  только Stage 7 API и существующую same-origin HttpOnly session/access gate.
- Category filters строятся из facet response и CategoryAttribute metadata;
  exact/boolean/range значения, manufacturer/location/availability, sorting и
  progressive loading сохраняются в детерминированном URL state.
- Equipment cards показывают dynamic `card_visible` attributes и ясные
  available/custody/total summaries; detail использует `detail_visible`
  attributes и безопасную внешнюю datasheet-ссылку.
- Telegram wrapper расширен BackButton lifecycle и safe-area integration без
  изменения vendored SDK loading/failure behavior.
- Добавлены focused behavior tests для API encoding, catalog shell, фильтров,
  карточек, detail/back navigation и Telegram BackButton.
- Focused remediation устранил cross-owner URL-state races: debounced search
  меняет только `q`, sorting — только `sort/order`, FilterSheet — только
  filter-owned state; updates применяются поверх актуальных `URLSearchParams`.
- Search input больше не remount-ится после debounce commit; regression tests
  покрывают сохранение focus, pending search + sort/filter и внешний URL state.
- Facets больше не показывают previous-query counts как актуальные во время
  перехода на новый query; item-list progressive loading при этом сохранён.
- Выдуманный `SI` brand mark заменён официальными black/white Spikatel SVG из
  предоставленного brand archive; assets поставляются локально same-origin.
- Backend, migrations, infrastructure и реальные inventory data не изменялись.
- Stage 8A remediation local gate PASS: frontend lint `0 warnings / 0 errors`,
  typecheck PASS, focused regressions `17/17`, full frontend suite `39/39`,
  production build PASS и `git diff --check` PASS.
- Focused remediation review закрыт с `P0=0`, `P1=0`.
- PR #15 Stage 8A прошёл required CI, merged и был развёрнут в production.
- Реальный Telegram Mini App viewport smoke подтвердил catalog landing,
  safe-area, bottom navigation, category/filter sheet и public frontend path.
- Production smoke выявил оставшийся viewport polish: пустые facet sections,
  duplicated inline/native Telegram BackButton и browser-native number
  steppers.
- PR #17 закрыл эти findings; локальный gate после remediation:
  lint `0 warnings / 0 errors`, typecheck PASS, focused tests `17/17`,
  full frontend suite `42/42`, production build PASS.
- Telegram entry UX завершён отдельным parallel slice: PR #16 добавил persistent
  `/start` state, deletion/replacement semantics и stale-start collapse;
  PRs #18/#19 уточнили message-effect behavior; PR #20 добавил финальную
  branded image-card через `sendPhoto`.
- Production PostgreSQL последовательно доведён до migration head
  `f1a2b3c4d5e6`.
- Перед финальной `/start` migration создан rollback checkpoint
  `/home/install/.dc-inventory-db-backups/pre-start-image-c8d77f8.dump`;
  размер 105K, SHA-256
  `0f70a52f874b7b7f1437314089c0e6115126aa8d12658e185e866b6f9bb65c4f`;
  `pg_restore --list` внутри PostgreSQL container PASS.
- Финальный production source:
  `c8d77f8cf34f89b7e54f668619319db26de5fc0b`.
- Production runtime checkpoint: backend/web/PostgreSQL healthy,
  telegram-worker/maintenance-worker running, health/live/ready PASS.
- Cloudflare Telegram Gateway production version:
  `a738702b-e731-48be-9576-e3485d1239f4`.
- Mac, GitHub и production checkout синхронизированы с `main`; obsolete
  Stage 8A/start branches удалены и production remote-tracking refs pruned.
- Stage 8A и branded Telegram entry UX production accepted 2026-09-03.
  Следующий продуктовый slice — Stage 8B. Full Playwright multi-viewport/E2E
  остаётся отдельным final Stage 8 gate.

## 2026-09-03 — Stage 8B implemented locally

- Read-only audit всех 23 строк authoritative SFP workbook подтвердил 265
  физических модулей и 10 manufacturers; workbook не изменялся, не копировался
  в repository и не использовался для stock/catalog seed.
- Migration `a2b3c4d5e6f7` добавила lossless speed/reach/wavelength profiles,
  optional nominal wavelength и exact `MPO`/`MPO/PC` connector semantics.
- TEXT validation получила metadata-controlled сохранение internal whitespace;
  обычная normalization осталась прежней.
- Реализованы role-aware Admin create/edit/archive/unarchive, metadata-driven
  dynamic form, inline Manufacturer и backend duplicate-candidate flow.
- Item detail показывает paginated warehouse projections по Location/holder и
  SERIAL units; «Моё» использует внутренний `User.id` для QUANTITY/SERIAL.
- Playwright acceptance добавлен для Telegram Desktop narrow, Android-like,
  iPhone-like и desktop/admin, включая BackButton, retry/empty, safe bottom
  navigation и horizontal overflow assertions; suite включён в frontend CI.
- Final local gates: Ruff PASS, strict mypy `107` files PASS, backend Pytest
  `233/233` PASS, frontend Vitest `49/49` PASS, production build PASS и
  Playwright `8/8` executed scenarios PASS (`12` inapplicable project
  combinations skipped). Fresh PostgreSQL migration upgrade/check,
  downgrade/re-upgrade/check PASS.
- Stage 8 implementation complete locally / ready for review. Production
  baseline `c8d77f8cf34f89b7e54f668619319db26de5fc0b` и production migration
  head `f1a2b3c4d5e6` не изменялись; production acceptance не заявляется.

## 2026-09-03 — Stage 8B production close

- Второй ручной audit/remediation cycle закрыт: все findings F01–F35
  разобраны, `SECOND_AUDIT_FINDINGS_REMAINING=0`.
- Final pre-PR consolidated gate PASS: backend Ruff/mypy/migrations PASS,
  PostgreSQL integration suite `277/277` PASS, frontend Vitest `64/64` PASS,
  production-Nginx Playwright PASS, Telegram Gateway PASS и
  production-shaped runtime PASS.
- PR #22 `Stage 8B: catalog UX, runtime hardening and audit remediation`
  прошёл четыре required checks: backend, frontend, runtime и
  telegram-gateway; merge commit `d7a95f6f6d7b5a232fa545ab9011f86858e7da08`.
- Push CI merge-коммита также завершён успешно четырьмя jobs.
- Перед production migration подтверждён head `f1a2b3c4d5e6`; warehouse
  journal/projections были пусты: movements, movement_lines, inventory_units
  и stock_balances — по `0`.
- Создан локальный rollback checkpoint
  `/opt/dc-inventory/backups/pre-stage8b-d7a95f6.dump`, размер около 106K, SHA-256
  `f595c6211f2ed40c4267555131d093e0d5e4a98ee8e45e10e3bb2a6339dc9d78`; `pg_restore --list` PASS.
- Production checkout обновлён на runtime source
  `d7a95f6f6d7b5a232fa545ab9011f86858e7da08`.
- PostgreSQL runtime переведён на pinned PostgreSQL 18 image digest из
  production Compose.
- Production migration `f1a2b3c4d5e6 -> a2b3c4d5e6f7` PASS;
  least-privilege grants повторно применены.
- Backend, web, telegram-worker и maintenance-worker пересозданы;
  backend/web/PostgreSQL healthy, health/live/ready PASS.
- После deploy подтверждены runtime UID boundaries, secret isolation,
  отсутствие host listeners `8000/5432`, CSP/Permissions-Policy и
  maintenance `technical retention` iteration.
- Warehouse counts до/после deploy совпали: `0/0/0/0`.
- `cloudflared` active; production checkout clean.
- Реальный Telegram `/start` acceptance PASS: branded welcome приходит,
  кнопка открывает Mini App, актуальный Stage 8B интерфейс открывается
  успешно.
- Stage 8B production accepted 2026-09-03.
- Automated off-VM PostgreSQL backup, real isolated restore и projection
  reconciliation остаются незакрытым Stage 15 production-data gate;
  `REAL_INVENTORY_ENTRY=BLOCKED`.
