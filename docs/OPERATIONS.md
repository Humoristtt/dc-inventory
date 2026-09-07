# Operations Runbook — Spikatel Inventory

## Source / deploy policy

Production VM не является development-машиной.

Runtime-changing deploy выполняется только из конкретного SHA после:

1. final local gate;
2. Pull Request CI;
3. review;
4. merge в `main`.

Repository остаётся public до завершения connector-dependent review,
merge/deploy и GitHub hardening. Перевод в private — последний шаг.

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

Stages 4–8B, branded Telegram `/start` и post-8B UX приняты в production.

Migration head:

    a2b3c4d5e6f7

Stage15A automated off-VM backup: `PASS`.
Stage15B real isolated restore: `PASS`.
Stage15C: `ACTIVE`.

AUD-01 production acceptance:

    REAL_INVENTORY_MUTATIONS_ENABLED=false
    REAL_INVENTORY_ENTRY=BLOCKED_PENDING_NEXT_ROADMAP
    pre-real-data inventory rows=0
    production health=PASS

Exact production checkout и runtime image provenance являются отдельным
operational evidence.

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

Текущий accepted desktop/mobile contract:

- обычный старт — `expand()` без автоматического true fullscreen;
- при viewport >= 400 CSS px доступен явный fullscreen toggle;
- `requestFullscreen()` вызывается только действием пользователя;
- в fullscreen CTA переключается на `exitFullscreen()`;
- при viewport < 400 CSS px fullscreen CTA скрыт;
- Escape используется только для внутренних dismissable layers;
- catalog не создаёт декоративных боковых borders при расширении desktop окна;
- первый переход landing → category начинается с верхней позиции страницы;
- mobile category cards сохраняют индексы `01`, `02`, ... без тяжёлых glyph blocks.

Cloudflare Telegram Gateway при этих frontend-only UX изменениях не менялся.

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

Скрипт read-only.

Запуск:

- перед первым real inventory entry;
- после restore;
- при подозрении на projection drift.

Ожидается zero rows.

Любая возвращённая строка означает расхождение между immutable movement journal
и текущей stock_balances projection.

Если drift найден:

1. остановить inventory mutations;
2. не выполнять автоматический repair;
3. сохранить backup/snapshot;
4. расследовать divergence;
5. определить controlled repair.

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
    STAGE15C=ACTIVE
    REAL_INVENTORY_ENTRY=BLOCKED_PENDING_NEXT_ROADMAP

Stage 15 implementation и acceptance ведутся по
`docs/STAGE15_PLAN.md`.

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

Эта процедура реально выполнена для Stage15B. Повторная final production
reconciliation и остальные Stage15C checks остаются обязательными перед снятием
production-data gate.

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

После merge/deploy/smoke:

1. main branch protection/rules;
2. required CI;
3. запрет непроверенного direct push;
4. clean/current `main`;
5. repository visibility — отдельное explicit решение перед снятием real-inventory gate и перед любой операцией с реальными данными.

## Перед первым real inventory entry

- [x] Stage 8B + post-8B UX production accepted;
- [x] migration head `a2b3c4d5e6f7`;
- [x] Stage15A automated off-VM backup;
- [x] first scheduled automatic backup;
- [x] Stage15B real isolated restore;
- [x] restore reconciliation zero drift;
- [x] local backup hygiene;
- [x] branch protection + four required CI checks;
- [x] production DB roles/journal/host-exposure audit;
- [x] production reconciliation zero drift;
- [x] AUD-01 fail-closed mutation gate;
- [x] AUD-02 runtime provenance v2;
- [x] AUD-03 exact S3 lifecycle-prefix validation;
- [x] AUD-06 command-level recovery runbook;
- [x] AUD-08..13 canonical docs + freshness CI;
- [x] AUD-04 durable immutable application rollback artifact;
- [x] AUD-05 controlled backup failure drill;
- [x] AUD-07 stale inventory-source assumptions retired;
- [x] host/security hardening accepted; recorded findings retained;
- [x] final full source + production re-audit;
- [x] explicit Stage15 gate decision: KEEP_DISABLED_NEXT_ROADMAP;
- [x] real inventory operator action explicitly deferred to next roadmap; no import executed.

После technical hardening сохраняется fail-closed operational state:

    REAL_INVENTORY_MUTATIONS_ENABLED=false
    REAL_INVENTORY_ENTRY=BLOCKED_PENDING_NEXT_ROADMAP


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

## Repository visibility boundary — AUD-19

Текущее состояние:

    REPOSITORY_VISIBILITY_CURRENT=public

Принятое правило до любых реальных складских данных:

    REPOSITORY_VISIBILITY_BEFORE_REAL_INVENTORY=REASSESS_REQUIRED
    AUD19_DECISION=REASSESS_BEFORE_REAL_INVENTORY

Пока repository public, в Git нельзя помещать реальные inventory datasets,
exports, database dumps, backup artifacts, credentials, tokens или production
environment files.

До снятия `REAL_INVENTORY_MUTATIONS_ENABLED=false` и до любой отдельной
real-data operator action repository visibility должна быть явно пересмотрена.
Решение public/private принимается отдельно с повторной проверкой Git
history/current tree на secrets и операционные artifacts. Независимо от
visibility реальные inventory datasets, dumps, credentials и production
environment files в Git не помещаются.
