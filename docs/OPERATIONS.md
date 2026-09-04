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

Runtime source:

    9a9ec6a705473d8bd3521b01e6f602284ed9c375

Migration head:

    a2b3c4d5e6f7

Stages 4–8B, branded Telegram `/start` и post-8B UX foundations развёрнуты и
приняты в production. Финальный live Telegram UX smoke завершён 2026-09-04:
windowed default, user-triggered fullscreen toggle с обратным выходом,
visibility threshold 400 CSS px, responsive desktop/mobile layout и catalog
edge/initial-scroll remediation подтверждены.

Следующий активный production-data этап — Stage 15. Real inventory entry
остаётся заблокирован до automated off-VM PostgreSQL backup, isolated real
restore и zero-drift reconciliation.

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

Ожидается zero rows для:

- QUANTITY drift;
- SERIAL drift.

Если drift найден:

1. остановить inventory mutations;
2. не выполнять автоматический repair;
3. сохранить backup/snapshot;
4. расследовать divergence;
5. определить controlled repair.

## Backup gate

Stage15A storage boundary принят 2026-09-04:

- StorageGRID S3 endpoint `https://s3-msk-1.cloudstack.ru`;
- bucket `dc-inventory-prod-backups`;
- backup prefix `postgres/`;
- Object Lock `GOVERNANCE`, 7 days;
- lifecycle current versions 30 days;
- backup identity не имеет `DeleteObject`;
- backup identity не может изменять lifecycle.

Automation implementation:

- `ops/backup/dc-inventory-backup-s3`;
- `ops/backup/s3_stage15.py`;
- `dc-inventory-backup-s3.service`;
- `dc-inventory-backup-s3.timer`;
- daily schedule `02:30 Europe/Moscow`;
- `Persistent=true`;
- state files в `/var/lib/dc-inventory-backup`.

Automated production PostgreSQL backup пока не является закрытым acceptance
gate: требуется merge/production install, первый verified off-VM artifact и
реальный isolated restore.

Локальные pre-deploy rollback dumps на production VM используются как
операционный checkpoint, но **не заменяют** automated off-VM backup и real
restore acceptance. Последний pre-deploy rollback checkpoint для Stage 8B:
`/opt/dc-inventory/backups/pre-stage8b-d7a95f6.dump`, SHA-256
`f595c6211f2ed40c4267555131d093e0d5e4a98ee8e45e10e3bb2a6339dc9d78`, `pg_restore --list` PASS.

Этот artifact остаётся локальным rollback checkpoint конкретного deploy и
не заменяет automated off-VM backup / restore acceptance Stage 15.

Следовательно:

    REAL_INVENTORY_ENTRY=BLOCKED_STAGE15

Backup implementation должна обеспечить:

- automated schedule;
- artifact off-VM;
- controlled access;
- retention policy;
- observable success/failure;
- documented restore procedure.

Stage 15 implementation и acceptance ведутся по
`docs/STAGE15_PLAN.md`.

## Restore acceptance

До первого real inventory entry:

1. взять настоящий backup artifact;
2. создать isolated restore environment;
3. восстановить artifact;
4. проверить schema/Alembic state;
5. выполнить application consistency checks;
6. выполнить projection reconciliation;
7. получить zero drift;
8. записать результат в `docs/HISTORY.md`.

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
5. repository private — самым последним действием.

## Перед первым real inventory entry

- [x] Stage 8B merged через PR #22;
- [x] production deploy Stages 4–8B + Telegram entry UX PASS;
- [x] migration head `a2b3c4d5e6f7` verified;
- [x] DB roles verified;
- [x] Telegram smoke PASS;
- [x] maintenance iteration PASS;
- [ ] automated PostgreSQL backup PASS;
- [ ] artifact off-VM;
- [ ] real restore PASS;
- [ ] reconciliation zero drift;
- [x] branch protection configured;
- [x] production runtime code baseline `9a9ec6a705473d8bd3521b01e6f602284ed9c375` accepted;
- [x] production checkout clean и синхронизируется с protected `main`.

Только после этого production-data gate можно снять.
