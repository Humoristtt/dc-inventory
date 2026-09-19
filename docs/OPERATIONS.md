# Operations Runbook — Spikatel Inventory

Актуализировано 19.09.2026. Последняя документированная production Procurement проверка: checkout/runtime `6d9bafef494f910b9bd1ebea7c5b7cf45f853742`, Alembic `c3d4e5f6a7b8`. Source head `a9c0d1e2f3a4` — **другой контур**; локальные CP-07–12 не являются автоматически production acceptance. Исторические SHA/evidence — `docs/HISTORY.md`, Stage 15 — `docs/STAGE15_PLAN.md`.

    ALEMBIC_HEAD=c3d4e5f6a7b8
    SOURCE_ALEMBIC_HEAD=a9c0d1e2f3a4
    RBAC_CUTOVER=PASS
    PROCUREMENT_DEPLOYMENT=PASS
    REAL_INVENTORY_MUTATIONS_ENABLED=false

## Source/deploy policy

Production VM не является development environment. Runtime-changing deploy: проверенный change set → PR/required CI/review → approved immutable SHA → maintenance deployment → health/provenance/live smoke. Git push/sync не запускает приложение. Source-only docs/host-side `ops/` sync разрешён без image rebuild лишь при неизменных Docker build contexts/runtime source и проверенных host-side scripts.

CP-07: новый web image **не** разворачивать при старом Tunnel origin `http://localhost:8080`: TCP не доверяет клиентскому IP, пользователи разделят общий rate-limit bucket. Требуется согласованное переключение Tunnel и web на trusted Unix socket, фактическая проверка permissions/UID/GID и rollback (`docs/CP07_HTTP_SOCKET_MIGRATION.md`). Public Mini App hostname: `https://app.spik-inventory.ru`.

## PostgreSQL identities и права

Production имеет **пять** отдельных login identities: owner/migrator (`POSTGRES_USER`), backend runtime, Telegram worker, optional email worker и maintenance worker. Owner credentials не используются runtime services. Backend не может broad UPDATE/DELETE immutable warehouse journal, `telegram_updates` меняет только `processed_at`, notification payload immutable для runtime; journal sequence access минимален. Telegram и email worker не получают чужие outbox/warehouse права, maintenance ограничен bounded technical retention.

После успешной миграции `db-permissions` выполняет `psql -X --single-transaction -v ON_ERROR_STOP=1`. Legacy role (`POSTGRES_LEGACY_WORKER_USER`, прежнее фактическое имя требуется уточнить) получает NOLOGIN и REVOKE внутри транзакции; `pg_terminate_backend()` для её старых sessions выполняется **после COMMIT**. Ошибка SQL откатывает права, но уже завершённые sessions восстановить нельзя. Backend/workers ждут успешного exit permission service.

## Deploy sequence

1. Подтвердить approved target SHA, successful CI, immutable images, schema compatibility.
2. Получить fresh verified off-VM backup и определить rollback/forward-fix/abort criteria.
3. Если migration несовместима — остановить старый web/backend/workers до неё.
4. При healthy PostgreSQL выполнить Alembic upgrade head, затем `db-permissions`.
5. Проверить фактические ACL/legacy sessions, запустить только новый runtime.
6. При CP-07 одновременно перевести web и Tunnel ingress.
7. Проверить health, OWNER/auth, worker heartbeat, actual image IDs/labels, reconciliation и live Telegram; optional email отдельно.
8. Сохранить post-deploy backup/evidence.

RBAC migration `f8a9b0c1d2e3 -> a1b2c3d4e5f6` исторически выполнена и несовместима с pre-RBAC backend. Rollback после несовместимой миграции — forward-fix или verified pre-cutover backup/restore, не запуск старого image на новой схеме.

## Recovery OWNER rotation

Только guarded maintenance CLI `python -m app.bootstrap.recovery_owner_rotation`, без normal admin API. Нужны existing Telegram identity target без custody, fresh verified backup, остановленный application runtime и healthy DB. CLI требует current/target Telegram IDs, target UUID и token `ROTATE_RECOVERY_OWNER`. Одна transaction пишет immutable audit, переводит старого OWNER в ADMIN, target — в OWNER, отзывает sessions и проверяет singleton. После COMMIT **до запуска backend** необходимо изменить `ADMIN_TELEGRAM_USER_ID` в production `.env`; иначе recovery reconciliation fail-closed. Подробная команда — `docs/DEPLOYMENT.md`.

## Runtime и host acceptance

`postgres/backend/web` healthy; Telegram/maintenance workers running с актуальным heartbeat; optional email worker только при enablement; `migrate` и `db-permissions` exited 0; успешная `technical retention:` iteration. Host публикует лишь `127.0.0.1:8080`; backend `8000` и PostgreSQL `5432` не слушают host. `/healthz`, `/api/health/live`, `/api/health/ready` → HTTP 200. При PostgreSQL DOWN: live 200/ready 503; BACK — ready 200 без backend restart.

Последний принятый host security baseline (требуется фактическая проверка перед deploy):

- UFW active;
- default inbound deny / outgoing allow, SSH `22/tcp` allowlisted;
- `PermitRootLogin no`;
- `PasswordAuthentication no`;
- `PubkeyAuthentication yes`;
- `X11Forwarding no`;
- `GatewayPorts no`;
- `AllowTcpForwarding yes` сохраняется для административных SSH tunnels.

Docker loopback-only ports обязательны независимо от UFW. Запрет на слепое изменение SSH/UFW без плана доступа.

Репозиторий публичный: `REPOSITORY_VISIBILITY_CURRENT=public`. Реальные datasets, workbook, DB dumps, private/runtime-only identifiers, secrets, `.env` в Git запрещены. Public service identifiers, например Mini App hostname и публичный support username, допустимы по назначению. `main` защищён required CI; merged topic branches удаляются после acceptance. Visibility меняется только отдельным security/operational решением.

## Telegram / email smoke

Incoming: Telegram → Cloudflare/Tunnel → Nginx → FastAPI webhook → PostgreSQL update dedupe. Outgoing: DB notification outbox → Telegram worker → HTTPS Cloudflare Worker Gateway → Telegram Bot API. Production `TELEGRAM_GATEWAY_URL` обязан быть HTTPS; bot token не передаётся Telegram worker. Последняя историческая Gateway version `a738702b-e731-48be-9576-e3485d1239f4` не является live-статусом.

После runtime changes проверить реальный `/start`: incoming command удаляется best-effort, branded `sendPhoto` welcome содержит caption/WebApp button, публично доступен `/telegram/start-welcome.png`. Access: unknown user request → ADMIN notification → approve/reject → user notification → approved login. Synthetic Playwright не заменяет real Telegram acceptance CP-17.

Принятый UI contract: Telegram/mobile shell использует expand/viewport APIs; desktop-capable runtime автоматически запрашивает fullscreen там, где Telegram Desktop поддерживает его. Fullscreen control — в header toolbar; Escape закрывает `[data-escape-dismiss]`, затем fullscreen; общий branded header/controls — во всех основных pages.

Уведомления Telegram и optional Graph email имеют **at-least-once** semantics: dedupe key предотвращает duplicate enqueue, но потерянное подтверждение внешнего сервиса может вызвать повторное сообщение/письмо. Exactly-once Telegram delivery не заявляется; такой контракт потребовал бы отдельной durable idempotency/reconciliation на внешней границе. `DEAD` после max attempts, explicit access requeue — отдельно. Email по умолчанию выключен `EMAIL_DELIVERY_ENABLED=false`, production Graph/live acceptance не проведены.

## Retention и reconciliation

Retention defaults: auth sessions 7 d, processed Telegram updates 30 d, terminal outbox 90 d, access callbacks 30 d, batch 1000, interval 3600 s. Maintenance singleton — PostgreSQL advisory transaction lock; immutable warehouse journal не удаляется.

`backend/scripts/reconcile_inventory_projections.sql` read-only сверяет stock/custody с immutable journal. После warehouse migrations/restore/data operations или при подозрении на drift нормальный результат zero rows. Drift — blocker: regular mutations disabled, fresh backup/evidence, расследование, не automated repair.

## S3 backup и recovery

Stage15A automated off-VM backup и исторический Stage15B isolated restore — PASS. StorageGRID endpoint `https://s3-msk-1.cloudstack.ru`, bucket `dc-inventory-prod-backups`, prefix `postgres/`; Object Lock GOVERNANCE 7 d, current lifecycle 30 d, noncurrent 1 d. Backup identity не имеет DeleteObject, bypass retention и lifecycle changes. Timer ежедневно 02:30 Europe/Moscow, `Persistent=true`, state `/var/lib/dc-inventory-backup`; постоянные локальные dumps запрещены.

Tools: `ops/backup/dc-inventory-backup-s3`, `ops/backup/s3_stage15.py`; runbook `docs/RECOVERY_RUNBOOK.md`, executable `ops/recovery/rehearse_restore.sh`. CP-11 локально добавил manifest application/type/key/hash/size/runtime validation, isolated credential/cleanup, session revocation, exact image check. Реальный повторный S3/production rehearsal и восстановление approved external configuration остаются OPEN. Restore не монтирует production volume и использует schema-version-matched reconciliation SQL из exact backend image.

## Initial production inventory bootstrap — accepted

    INITIAL_PRODUCTION_BOOTSTRAP=PASS
    POST_IMPORT_RECONCILIATION=ZERO_DRIFT
    POST_IMPORT_BACKUP=PASS
    TELEGRAM_VISUAL_ACCEPTANCE=PASS
    INITIAL_PRODUCTION_BOOTSTRAP=DO_NOT_RERUN
    REAL_INVENTORY_MUTATIONS_ENABLED=false

External operator workbook был проверен; guarded one-shot bootstrap создал location + opening RECEIPT, прошли counts/quantity, zero drift, health и verified backup. Workbook/data identifiers не публикуются. Для regular warehouse mutation API требуется самостоятельное go-live решение.
