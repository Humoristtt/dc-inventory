# Operations Runbook — Spikatel Inventory

## Source / deploy policy

Production VM не является development-машиной.

Runtime-changing deploy выполняется только из конкретного SHA после:

1. final local gate;
2. Pull Request CI;
3. review;
4. merge в `main`.

Repository visibility является отдельным operational решением.

Текущий repository может оставаться public только при строгой границе:
никаких inventory datasets, workbook contents, database dumps, credentials,
tokens, production environment files и runtime-only identifiers в Git.

## PostgreSQL identities

Production использует четыре отдельные DB identity.

### Owner / migrator

Только:

- Alembic;
- permission bootstrap;
- controlled DB administration.

### Backend runtime

Application role.

Критические boundaries:

- нет broad UPDATE/DELETE warehouse journal;
- `telegram_updates` — только `UPDATE(processed_at)`;
- notification recovery — UPDATE только delivery-state columns;
- payload `notification_outbox` менять нельзя;
- sequence access только к требуемой journal sequence.

### Telegram worker

Только notification delivery contract.

### Maintenance worker

Только bounded cleanup технических данных и необходимый read-only
`access_requests`.

Warehouse mutation privileges отсутствуют.

## Current production baseline

Warehouse Domain V2 принят в production.

Current schema:

    ALEMBIC_HEAD=c5d6e7f8a9b0

Stage15:

    STAGE15=TECHNICAL_HARDENING_COMPLETE
    STAGE15A=PASS
    STAGE15B=PASS
    STAGE15C=COMPLETE

Initial production inventory bootstrap:

    INITIAL_PRODUCTION_BOOTSTRAP=PASS
    POST_IMPORT_RECONCILIATION=ZERO_DRIFT
    POST_IMPORT_BACKUP=PASS
    TELEGRAM_VISUAL_ACCEPTANCE=PASS

Authoritative workbook остаётся external operator input и не хранится в Git.

Regular warehouse mutation API остаётся закрыт:

    REAL_INVENTORY_MUTATIONS_ENABLED=false

Initial bootstrap был выполнен отдельным guarded one-shot CLI и не открывал
regular mutation gate.

Exact production checkout и runtime image provenance являются отдельными
operational facts. Исторические acceptance SHA фиксируются в `docs/HISTORY.md`,
а текущее состояние проверяется непосредственно на production.

## Deploy sequence

1. подтвердить target SHA;
2. обновить production checkout;
3. проверить `.env`;
4. выполнить `alembic upgrade head`;
5. выполнить idempotent `db-permissions`;
6. запустить runtime;
7. дождаться health;
8. выполнить smoke;
9. при warehouse changes выполнить reconciliation.

## Runtime acceptance

Containers:

- postgres healthy;
- backend healthy;
- web healthy;
- telegram-worker running;
- maintenance-worker running;
- migrate exited 0;
- db-permissions exited 0.

Host exposure:

- `127.0.0.1:8080` — разрешён;
- backend `8000` — не публикуется;
- PostgreSQL `5432` — не публикуется.

HTTP:

    /healthz            -> 200
    /api/health/live    -> 200
    /api/health/ready   -> 200

## Telegram smoke

Incoming:

    Telegram
      -> Cloudflare
      -> webhook
      -> FastAPI
      -> PostgreSQL

Outgoing:

    NotificationOutbox
      -> telegram-worker
      -> HTTPS Cloudflare Gateway
      -> Telegram Bot API

Production `TELEGRAM_GATEWAY_URL` обязан быть HTTPS.

После Telegram runtime changes минимум проверяется `/start`: incoming command
удаляется, branded `sendPhoto` welcome приходит с ожидаемой caption/button и
Mini App открывается по WebApp CTA.

Текущая production Cloudflare Telegram Gateway version:

    a738702b-e731-48be-9576-e3485d1239f4

После access-flow changes:

1. unknown user request;
2. ADMIN notification;
3. approve/reject;
4. user notification;
5. approved login.

### Telegram Mini App UX acceptance

Текущий accepted Warehouse UI contract:

- Telegram/mobile shell использует `expand()` и поддерживаемые viewport APIs;
- desktop-capable runtime автоматически запрашивает fullscreen там, где
  Telegram Desktop это поддерживает;
- fullscreen control находится внутри page header toolbar, а не fixed overlay;
- CTA корректно переключает request/exit fullscreen;
- Escape сначала закрывает последний внутренний `[data-escape-dismiss]` layer;
- если внутреннего dismiss-layer нет и fullscreen активен, Escape завершает
  fullscreen;
- если закрывать нечего, Escape не запускает случайную navigation action;
- category landing, category page, movements, locations, item form и item detail
  используют единый branded header contract;
- desktop item/location forms используют согласованную responsive geometry;
- smart suggestions не ограничивают возможность ручного ввода допустимого
  значения;
- catalog desktop layout не создаёт декоративных боковых borders;
- landing → category navigation начинает страницу сверху;
- mobile category cards сохраняют компактные числовые индексы.

Synthetic frontend Playwright не считается доказательством реального Telegram
host behavior. Для production UX acceptance используется отдельный real Telegram
visual smoke.

Cloudflare Telegram Gateway не меняется при frontend-only warehouse UX changes.

## Technical retention

Defaults:

- auth sessions — 7 days;
- processed Telegram updates — 30 days;
- terminal outbox — 90 days;
- terminal access callbacks — 30 days;
- batch — 1000;
- interval — 3600 seconds.

Worker использует PostgreSQL advisory transaction lock для singleton execution.

Проверка после deploy:

- maintenance-worker running;
- в logs есть successful `technical retention:` iteration.

Warehouse journal в retention target set не входит.

## Projection reconciliation

Canonical script:

    backend/scripts/reconcile_inventory_projections.sql

Скрипт read-only и пересчитывает quantity projection из immutable
Movement/MovementLine journal.

Запуск обязателен:

- после warehouse-affecting migrations;
- после restore;
- после controlled initial/data bootstrap;
- перед и после risky inventory data maintenance;
- при подозрении на projection drift.

Ожидается zero rows.

Любая возвращённая строка означает расхождение между immutable movement journal
и `stock_balances`.

Если drift найден:

1. regular inventory mutations остаются/переводятся в disabled state;
2. автоматический repair не выполняется;
3. сохраняется fresh backup/evidence;
4. расследуется divergence;
5. controlled repair проектируется отдельно.

## Backup gate

Stage15A automated off-VM PostgreSQL backup принят в production.

Storage boundary:

- StorageGRID S3 endpoint `https://s3-msk-1.cloudstack.ru`;
- bucket `dc-inventory-prod-backups`;
- backup prefix `postgres/`;
- Object Lock `GOVERNANCE`, 7 days;
- lifecycle current versions 30 days;
- lifecycle rules обязаны покрывать exact configured prefix `postgres/`;
- noncurrent versions 1 day;
- backup identity не имеет `DeleteObject`;
- backup identity не может изменять lifecycle.

Automation:

- `ops/backup/dc-inventory-backup-s3`;
- `ops/backup/s3_stage15.py`;
- `dc-inventory-backup-s3.service`;
- `dc-inventory-backup-s3.timer`;
- daily schedule `02:30 Europe/Moscow`;
- `Persistent=true`;
- timer active и enabled;
- state files в `/var/lib/dc-inventory-backup`.

Первый verified off-VM artifact и реальный isolated restore приняты в Stage15A/B.

Первый автоматический scheduled production run также доказан:

- started `2026-09-04T23:30:01Z`
  (`2026-09-05 02:30 Europe/Moscow`);
- dump
  `postgres/full/2026/09/04/dc-inventory-20260904T233001Z.dump`;
- size `100901` bytes;
- SHA-256
  `4c54098b53a2636614373b44f7894d3f95a32e334c964900a14dec3b5539ce74`;
- Alembic `a2b3c4d5e6f7`;
- remote verification PASS.

Local backup policy после Stage15C hygiene checkpoint:

- permanent local PostgreSQL dump collection отсутствует;
- verified StorageGRID S3 artifacts являются authoritative DB recovery source;
- backup execution создаёт только temporary
  `/var/tmp/dc-inventory-backup.XXXXXX` workdir;
- temporary dump удаляется cleanup trap после завершения процесса;
- `/var/lib/dc-inventory-backup/status.json` и `last-success.json` являются
  state/observability, а не backup artifacts;
- unmanaged manual PostgreSQL dumps на production VM не должны накапливаться;
- пустые legacy directories `/home/install/.dc-inventory-db-backups` и
  `/opt/dc-inventory/backups` удалены 2026-09-06;
- единственный сохранённый local rollback artifact:
  `/home/install/.dc-inventory-env-backups/env-pre-stage6-deploy`;
- этот artifact относится к environment/config rollback, не к PostgreSQL;
- его SHA-256:
  `350535df2631887159486587c13758ceb83c376cecb02967ab0d671cf3bd29f7`.

Следовательно:

    STAGE15A=PASS
    STAGE15B=PASS
    STAGE15C=COMPLETE
    INITIAL_PRODUCTION_BOOTSTRAP=PASS
    REGULAR_MUTATION_GATE=DISABLED

Stage 15 historical implementation/acceptance хранится в
`docs/STAGE15_PLAN.md`. Текущий post-Stage15 state фиксируется этим runbook и
`docs/HISTORY.md`.

## Restore acceptance

Stage15B real isolated restore acceptance: `PASS`.

Canonical command-level recovery procedure:

    docs/RECOVERY_RUNBOOK.md

Accepted procedure:

1. взять настоящий verified off-VM backup artifact;
2. проверить manifest и SHA-256;
3. создать isolated PostgreSQL restore environment;
4. не публиковать PostgreSQL host port;
5. восстановить artifact через `pg_restore`;
6. проверить schema/Alembic state;
7. проверить critical row counts/invariants;
8. выполнить application compatibility check;
9. выполнить canonical projection reconciliation;
10. получить zero rows от canonical inventory projection reconciliation;
11. удалить temporary restore environment только после сохранения evidence;
12. записать acceptance в `docs/HISTORY.md`.

Эта процедура реально выполнена для Stage15B и является historical evidence
первого real isolated restore acceptance.

После появления production inventory каждый последующий restore rehearsal
проверяет выбранный artifact по его manifest: Alembic head, critical row
counts/invariants, application compatibility и canonical zero-drift
reconciliation.

Restore rehearsal сам не открывает regular mutation gate.

## Failure boundaries

### PostgreSQL unavailable

Expected:

    live  -> 200
    ready -> 503

После возврата PostgreSQL readiness должна восстановиться без рестарта backend.

### Telegram Gateway unavailable

Warehouse DB transaction остаётся достоверной.
Outbox выполняет bounded retries.
После max attempts row становится `DEAD`.

Access ADMIN notification может быть controlled-requeued повторным explicit
access request.

### Maintenance worker unavailable

Warehouse runtime продолжает работать, но технический cleanup остановлен.

### Projection drift

Data-integrity blocker. Inventory mutations останавливаются.

## GitHub hardening

После accepted merge/deploy/smoke:

1. main branch protection/rules;
2. required CI;
3. запрет непроверенного direct push;
4. clean/current `main`;
5. merged topic branches удаляются после acceptance; целевое состояние между
   change sets — только `main`;
6. public visibility допустима только при
   `REPOSITORY_DATA_POLICY=NO_REAL_INVENTORY_DATA_IN_GIT`; изменение visibility
   является отдельным explicit security/operational решением.

## Initial production inventory bootstrap — accepted

Pre-data Stage15 checklist исторически завершён.

После него отдельным post-Stage15 change set выполнены:

- Warehouse Domain V2 production rollout;
- current migration head `c5d6e7f8a9b0`;
- external workbook validation;
- guarded production bootstrap implementation;
- required local PostgreSQL gates;
- PR/CI acceptance;
- exact production backend image build/provenance verification;
- read-only empty-domain preflight;
- fresh pre-import verified off-VM backup;
- one-shot initial RECEIPT bootstrap;
- post-import counts/quantity verification;
- canonical reconciliation with zero drift;
- regular mutation gate confirmation `false`;
- fresh verified post-import off-VM backup;
- real Telegram visual acceptance.

Operational rule after acceptance:

    INITIAL_PRODUCTION_BOOTSTRAP=DO_NOT_RERUN
    REAL_INVENTORY_MUTATIONS_ENABLED=false

Normal warehouse operations require a separate go-live decision.

## Stage15C host security baseline — AUD-17

Read-only production audit recorded the following state:

    HOST_OS=Ubuntu_24.04.4_LTS
    HOST_KERNEL=6.8.0-139-generic
    SSH_PORT=22
    SSH_ROOT_LOGIN=DISABLED
    SSH_PASSWORD_AUTH=DISABLED
    SSH_KBD_INTERACTIVE_AUTH=DISABLED
    SSH_PUBKEY_AUTH=ENABLED
    SSH_X11_FORWARDING=ENABLED_RECORDED_FINDING
    SSH_TCP_FORWARDING=ENABLED_RECORDED_FINDING
    UFW_STATUS=INACTIVE_RECORDED_FINDING
    APP_HOST_BIND=127.0.0.1:8080
    POSTGRES_HOST_PORT=NONE
    AUD17_HOST_AUDIT=READ_ONLY_RECORDED

На всех интерфейсах из постоянных TCP listeners доступен SSH `22/tcp`.
Web runtime опубликован только на loopback `127.0.0.1:8080`.
PostgreSQL host port не публикуется.

`cloudflared` использует outbound tunnel sockets и loopback listener
`127.0.0.1:20241`; это не application host publication.

UFW во время read-only audit выключен. Это записанный finding, а не утверждение
о включённом host firewall. `X11Forwarding=yes` и `AllowTcpForwarding=yes`
также не менялись в рамках read-only проверки.

На момент audit доступны обновления Docker/containerd, включая Docker
`29.8.0` при production `29.7.2`. Обновление daemon не выполняется
автоматически внутри Stage15 audit. Необходимость обновления оценивается
вместе с vulnerability scan и final production acceptance.

AUD-23 precondition recheck completed 2026-09-07: listeners, SSH effective
config, host firewall state и host-published application ports проверены
повторно; recorded findings не изменились.

## Repository visibility boundary

Current repository state:

    REPOSITORY_VISIBILITY_CURRENT=public
    REPOSITORY_DATA_POLICY=NO_REAL_INVENTORY_DATA_IN_GIT

Repository visibility остаётся отдельным security/operational решением.

Initial production bootstrap был выполнен без помещения real inventory source в
Git. External workbook, его hash contract, реальные строки, runtime actor/location
identifiers и database contents остаются вне repository.

Независимо от public/private visibility запрещено коммитить:

- authoritative inventory workbook и его копии;
- exports реального склада;
- PostgreSQL dumps;
- backup artifacts;
- `.env` production;
- credentials/tokens/private keys;
- runtime-only secrets/identifiers без необходимости.

Repository visibility сама по себе не является warehouse database mutation
механизмом. Regular inventory operations регулируются backend authorization,
database privileges и `REAL_INVENTORY_MUTATIONS_ENABLED`.
