# Развёртывание Spikatel Inventory

Production VM не является средой разработки. Изменения проходят Mac → GitHub → проверенный exact commit/CI → согласованный production cutover. VM имеет read-only Deploy Key; публикация ветки, слияние и синхронизация исходников **не** разворачивают приложение.

## Подтверждённые границы

Последняя документированная проверка работающего Procurement runtime: checkout/image revision `6d9bafef494f910b9bd1ebea7c5b7cf45f853742`, Alembic `c3d4e5f6a7b8`. Это historical operational evidence, не автоматическая проверка состояния на сегодня. Текущий source Alembic head: `a9c0d1e2f3a4`; source-миграции и CP-07–12 не следует объявлять production state до отдельного deploy/runtime-provenance acceptance.

Warehouse Domain V2, initial inventory bootstrap, Stage15A off-VM backup и Stage15B historical isolated restore приняты. Initial bootstrap одноразовый; обычный warehouse API остаётся fail-closed:

    REAL_INVENTORY_MUTATIONS_ENABLED=false

Исторические события: `docs/HISTORY.md`; текущие незакрытые границы: `docs/AUDIT_0_12_REMEDIATION.md`, эксплуатация: `docs/OPERATIONS.md`.

## Runtime и сети

`compose.yaml` содержит PostgreSQL, миграцию, одноразовую выдачу прав, FastAPI, Nginx, Telegram worker, maintenance worker и необязательный email worker. PostgreSQL и backend не имеют опубликованных host-портов и находятся во внутренних Docker networks. На host опубликован только `127.0.0.1:8080` для web. Production backend работает как UID 10001, web — nginx; health: `/healthz`, `/api/health/live`, `/api/health/ready`.

Текущий, **ещё не переключённый**, Cloudflare Tunnel origin: `http://localhost:8080`. Публичный HTTPS Mini App: `https://app.spik-inventory.ru`. Token Tunnel — секрет, не хранится в Git.

### Обязательный CP-07 migration gate

Локально подготовленный Nginx различает недоверенный TCP `:8080` и trusted Unix-socket `/run/dc-inventory/ingress.sock`. TCP не доверяет клиентским `CF-Connecting-IP`/`X-Forwarded-Proto`; Unix применяет `set_real_ip_from unix:` и `real_ip_header CF-Connecting-IP`. Backend получает нормализованные proxy headers; rate limit использует `$remote_addr`, а HTTPS origin на Unix задаётся конфигурацией. Доступ к сокету ограничивается правами **родительского каталога**, не только самого socket file.

**Запрещено обновлять web image, сохраняя старый Tunnel → TCP origin:** пользователи окажутся в общем IP/rate-limit bucket. В одном согласованном change window нужно проверить реальные UID/GID cloudflared/nginx, socket directory и bind mount, переключить Tunnel на Unix origin вместе с web release, подтвердить внешний HTTP/Telegram smoke и rollback. Статус CP-07 в production — OPEN. Пошаговый план: `docs/CP07_HTTP_SOCKET_MIGRATION.md`; поддержку конкретного формата Unix origin cloudflared необходимо проверить на целевой установленной версии перед изменением production.

Nginx ограничивает общий API 30 rps/burst 60, auth/access mutations 10 rpm/burst 5, webhook 50 rps/burst 100; превышение — 429. HSTS `max-age=31536000`, без `includeSubDomains`/`preload`. Uvicorn доверяет proxy headers только за внутренним Nginx; прямой host access к backend запрещён. CPU/RAM каждого сервиса ограничиваются Compose `cpus`/`mem_limit` и при необходимости переопределяются через `*_CPUS_LIMIT`/`*_MEMORY_LIMIT`.

## Release integrity и supply chain

Внешние container images фиксируются одновременно human-readable tag и immutable manifest `sha256` digest; GitHub Actions — полными commit SHA. Изменение pin требует проверки upstream digest/commit и штатных runtime/CI gates.

`ops/release/build_release.py --env-file <env> --output <new-directory>` принимает **чистый checkout**; требует полный Git SHA, свободные release tags, валидные immutable Docker image IDs и label `org.opencontainers.image.revision` для backend/web/postgres. Публикует `release.json` и `release.env` лишь после успешной сборки/проверки всех трёх образов. При ошибке output directory не сохраняется, но уже созданные теги могут остаться в Docker daemon — проверять их отдельно, автоматически чужие images не удалять. Build script не выполняет deploy.

Альтернативная ручная сборка при согласованном runtime-changing deploy:

```bash
REVISION="$(git rev-parse HEAD)"
APP_REVISION="$REVISION" docker compose build backend postgres web
```

`ops/backup/runtime_provenance.py` сравнивает переданный `--production-checkout-sha` с **фактическим `git rev-parse HEAD`** в `--root`, затем получает запущенные image IDs и revision labels непосредственно из Docker images (а не из переопределяемых container labels). Telegram/maintenance workers должны совпадать с backend; email worker проверяется при включённой email delivery. Равенство текущего checkout SHA и старых image revisions не требуется **только** при разрешённом source-only sync: неизменные Docker build contexts/application runtime source, отдельно проверенные host-side `ops/` scripts. Production runtime provenance после деплоя — отдельная acceptance.

## Секреты и DB identity

Production `.env` создаётся только на VM, не коммитится и не печатается в logs. Owner/migrator identity использует `POSTGRES_USER`/`POSTGRES_PASSWORD`. Backend получает `POSTGRES_RUNTIME_USER`/`POSTGRES_RUNTIME_PASSWORD`; Telegram — `POSTGRES_TELEGRAM_WORKER_USER`/`POSTGRES_TELEGRAM_WORKER_PASSWORD`; optional email — `POSTGRES_EMAIL_WORKER_USER`/`POSTGRES_EMAIL_WORKER_PASSWORD`; maintenance — `POSTGRES_MAINTENANCE_USER`/`POSTGRES_MAINTENANCE_PASSWORD`. Все runtime роли least-privilege, без owner credentials. Для разового cutover старой общей worker identity задаётся `POSTGRES_LEGACY_WORKER_USER`, по умолчанию `dc_inventory_worker`; если прежнее имя было нестандартным, оно указывается явно.

После успешного Alembic upgrade `db-permissions` применяет изменения ролей/прав через `psql -X --single-transaction -v ON_ERROR_STOP=1`. При ошибке SQL изменения откатываются; legacy role получает NOLOGIN и REVOKE транзакционно, а старые sessions завершаются **отдельным шагом только после успешного COMMIT**. Это действие над соединениями необратимо. Backend/workers зависят от успешного `db-permissions`. На новом сервере отсутствие legacy role нормально; обычным runtime ролям owner credentials не передавать.

Внутри Docker `DATABASE_URL` использует hostname `postgres`, например `postgresql+asyncpg://USER:PASSWORD@postgres:5432/DATABASE`. Никаких реальных credentials в документации.

### Telegram

Backend: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_INIT_DATA_MAX_AGE_SECONDS`, `ADMIN_TELEGRAM_USER_ID`, `NOTIFICATION_TELEGRAM_USER_ID`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_WEB_APP_URL`, параметры session cookie. `ADMIN_TELEGRAM_USER_ID` — singleton recovery OWNER, **не** получатель рабочих сообщений; операционный recipient — `NOTIFICATION_TELEGRAM_USER_ID` (APPROVED ADMIN/OWNER для inline access decisions). Frontend не получает bot token.

Telegram worker: `TELEGRAM_GATEWAY_URL`, `TELEGRAM_GATEWAY_SECRET`, timeout/poll/claim/max-attempts; не получает bot token и webhook secret. В production gateway URL — абсолютный HTTPS без credentials/query/fragment. Cloudflare Worker независимо хранит `BOT_TOKEN` и `GATEWAY_SECRET`; первый совпадает с backend bot token, второй является отдельным shared secret worker↔gateway. Ротация bot token требует согласованной замены обоих secret stores.

Incoming: Telegram → Cloudflare/Tunnel → Nginx → webhook `/api/telegram/webhook` → PostgreSQL update dedupe. Webhook сверяет `X-Telegram-Bot-Api-Secret-Token`. Outgoing: DB outbox → worker → Cloudflare Worker Telegram Gateway → Bot API. На Gateway allowlist: sendMessage, sendPhoto, deleteMessage, editMessageText, editMessageReplyMarkup, answerCallbackQuery; всё остальное deny. Gateway unavailable не отменяет warehouse transaction. Внешняя доставка — at-least-once, duplicate send при потере ответа возможен.

### Email

`EMAIL_DELIVERY_ENABLED=false` по умолчанию. API fail-closed, если выключен delivery или не заполнен Microsoft Graph config; email worker запускается только с explicit Compose profile `email`. Отдельная DB role не видит Telegram/warehouse mutation tables. Доставка email имеет retry/DEAD, но не exactly-once: при потере подтверждения Graph возможно повторное письмо. Production secrets/profile/live acceptance остаются OPEN.

### Recovery OWNER rotation

OWNER меняется только maintenance-only CLI `python -m app.bootstrap.recovery_owner_rotation`, не admin API. Нужны existing Telegram identity target, отсутствие custody у target, verified off-VM backup и остановленные web/backend/Telegram/maintenance workers при healthy PostgreSQL. Команда из target release image:

```bash
docker compose --env-file .env -f compose.yaml run --rm --no-deps backend \
  python -m app.bootstrap.recovery_owner_rotation \
  --current-telegram-user-id CURRENT_TELEGRAM_ID \
  --target-telegram-user-id TARGET_TELEGRAM_ID \
  --target-user-id TARGET_USER_UUID \
  --confirm ROTATE_RECOVERY_OWNER
```

Одна DB transaction под advisory lock переводит старого OWNER в ADMIN, target — в OWNER, записывает immutable role/access events, отзывает sessions и проверяет единственного OWNER. **После COMMIT, но до старта backend** изменить `ADMIN_TELEGRAM_USER_ID` в `.env`, иначе recovery reconciliation fail-closed.

## Миграции и controlled cutover

Migration `a1b2c3d4e5f6` изменила persisted `USER`→`ENGINEER`: она несовместима с pre-RBAC backend. Это **исторический** maintenance cutover, уже принятый; не запускать старый backend против мигрированной БД. При новых несовместимых миграциях соблюдать тот же принцип: точный target SHA + CI; свежий verified off-VM backup; immutable release; остановить несовместимый старый runtime; сохранить PostgreSQL healthy; Alembic upgrade head; `db-permissions`; новый runtime; health, OWNER/auth smoke; reconciliation и post-deploy backup по применимости.

Migration connection timeout budget: `MIGRATION_STATEMENT_TIMEOUT_SECONDS=300`, `MIGRATION_LOCK_TIMEOUT_SECONDS=5`, отдельно от runtime timeout. Destructive downgrade разрешается только при доказанном отсутствии новых данных; для RBAC и SFP profile migration fail-closed ограничения описаны в коде/тестах. Rollback после несовместимой миграции — forward-fix или verified pre-cutover backup/restore, **не** запуск старого image поверх новой схемы.

## Initial production inventory bootstrap

Первоначальный импорт выполнен 08.09.2026 и повторяться не должен. CLI `python -m app.bootstrap.production_inventory` — one-shot operator tool, не regular mutation API. Проверяет `APP_ENV=production`, Docker postgres boundary, закрытый `REAL_INVENTORY_MUTATIONS_ENABLED=false`, explicit confirmation, внешний workbook SHA/counts, existing APPROVED ADMIN, пустой warehouse, атомарное создание StorageLocation + opening RECEIPT, counts/quantity и zero-drift reconciliation **до commit**. Реальные source/workbook/actor/location identifiers не публикуются. Повторный запуск на наполненной БД — fail-closed.

## Проверка после deploy

```bash
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/api/health/live
curl --fail http://127.0.0.1:8080/api/health/ready
```

Все три — HTTP 200. `postgres/backend/web` healthy, Telegram/maintenance workers running, миграция и `db-permissions` exited 0, у maintenance есть успешная retention iteration. Backend UID 10001, web nginx, host не слушает backend `8000` и PostgreSQL `5432`. Сверить actual Git HEAD, image IDs/revisions и target release; при warehouse changes — reconciliation zero rows. После Telegram runtime changes — реальный `/start` через webhook/outbox/worker/Gateway, best-effort cleanup, branded `sendPhoto` с caption/WebApp button и доступность `/telegram/start-welcome.png`; access-flow smoke — request → ADMIN approve → notification → login.

Stage15A automated off-VM PostgreSQL backup и historical Stage15B isolated restore приняты. Перед рискованными schema/data changes обязателен **новый** verified backup и rollback/forward-fix plan. Новый полный restore из production S3 после CP-11 всё ещё требует отдельной проверки. Канонический runbook: `docs/RECOVERY_RUNBOOK.md`.
