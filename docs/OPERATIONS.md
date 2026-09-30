# Эксплуатация Spikatel Inventory

Этот документ описывает **как измерять и сопровождать live runtime**. Он намеренно не содержит старых production SHA и не считает прошлую приёмку доказательством текущего состояния.

## 1. Source и live production — разные состояния

Git отвечает на вопрос «что должно быть в release». Live production проверяется отдельно.

Нельзя выводить из Git:

- какой checkout сейчас на VM;
- какие image IDs реально запущены;
- какой Alembic head реально в production DB;
- включён ли mutation/email flag;
- свежая ли последняя backup;
- какой webhook/Tunnel route фактически активен.

Перед изменением production эти значения измеряются заново.

## 2. Ожидаемый runtime

Штатные services:

- postgres;
- backend;
- web;
- telegram-worker;
- maintenance-worker;
- optional email-worker.

One-shot jobs:

- migrate;
- db-permissions.

Нормально, если one-shot jobs завершены и не находятся в running state.

## 3. Health endpoints

### Web

```text
GET /healthz
```

Ожидается `200` и `ok`.

### Backend liveness

```text
GET /api/health/live
```

Показывает, что application process жив.

### Backend readiness

```text
GET /api/health/ready
```

Readiness проверяет:

- database connection;
- DB Alembic head == source image head;
- критические columns;
- критические triggers/functions/collation.

При несовместимой DB ready обязан вернуть 503, даже если process жив.

## 4. Runtime provenance

Собрать:

```bash
python3 ops/backup/runtime_provenance.py   --root /path/to/checkout   --env-file /path/to/production.env   --output /restricted/path/runtime-provenance.json   --production-checkout-sha <measured-full-sha>
```

Файл содержит runtime image IDs/revision labels. Не публиковать его в публичный Git, если он содержит private/runtime-only identifiers.

Сравнение с approved release:

```bash
python3 ops/release/verify_release_runtime.py   --release-manifest /restricted/path/release.json   --runtime-provenance /restricted/path/runtime-provenance.json
```

## 5. Ingress

Ожидаемая production topology:

```text
Internet
  │
  ▼
host Nginx
  │
  ▼
/var/lib/dc-inventory-ingress/ingress.sock
  │
  ▼
web Nginx
  │
  ▼
backend
```

Read-only host verification:

```bash
sudo python3 ops/host_ingress/verify.py
```

Verifier проверяет installed Nginx config/hook, service state, certificate paths, ingress directory/socket ownership/mode и отсутствие unexpected container port bindings.

Public user ingress не должен зависеть от client-provided forwarded headers.

## 6. Host security

Перед release/incident response **измерить повторно**, а не ссылаться на старый audit.

Ожидаемый baseline:

- UFW active;
- `PermitRootLogin no`;
- `PasswordAuthentication no`;
- `X11Forwarding no`;
- `GatewayPorts no`;
- `AllowTcpForwarding yes` допускается только если нужен операторский SSH forwarding;
- PostgreSQL, backend и production web не имеют публичных application ports.

Если live state отличается, это отдельный security finding.

## 7. Docker boundaries

Проверить:

- `read_only`;
- `cap_drop=ALL`;
- `no-new-privileges`;
- pids/resource limits;
- network membership;
- host port bindings;
- image IDs;
- OCI revision labels.

Telegram/email workers имеют egress; backend и maintenance — нет.

## 8. PostgreSQL identities

Отдельно измерить effective privileges для:

- owner;
- application runtime;
- Telegram worker;
- email worker;
- maintenance worker.

Критичные отрицательные проверки:

- runtime не создаёт objects в schema;
- runtime не UPDATE/DELETE warehouse history;
- runtime не DML-ит stock/custody projection напрямую;
- Telegram worker не читает email outbox;
- email worker не читает Telegram/domain tables;
- maintenance не читает/удаляет movements;
- legacy delivery role не имеет LOGIN/старых grants.

## 9. Mutation state

Проверить фактическое значение:

```text
REAL_INVENTORY_MUTATIONS_ENABLED
```

Default configuration — `false`.

Нельзя временно включать флаг «для проверки» на production, если это не часть утверждённого business operation.

## 10. Warehouse consistency

Read-only reconciliation:

```text
backend/scripts/reconcile_inventory_projections.sql
```

Нормальный результат — zero drift между immutable journal и:

- stock_balances;
- user_item_custody_balances.

Любой drift — incident. Не чинить projection ручным UPDATE; сначала установить root cause и использовать корректный repair path.

## 11. Workers

Каждый long-running worker имеет container healthcheck на heartbeat file.

Контролировать:

- container health;
- последнюю worker iteration;
- restart count;
- error logs;
- queue age.

### Telegram delivery

Telegram использует **at-least-once** delivery. Exactly-once не обещается: при **потере ответа внешнего провайдера** worker не может знать, был ли side effect выполнен, и retry способен создать повторное внешнее сообщение.

Dedupe key предотвращает дублирование outbox intent, но не внешнего side effect после потерянного response.

Контролировать PENDING/PROCESSING/DEAD и attempts.

### Email

Email worker должен отсутствовать или быть stopped, пока:

```text
EMAIL_DELIVERY_ENABLED=false
```

Включение требует отдельного Graph config и реального delivery smoke.

## 12. Telegram webhook

Webhook endpoint проверяет dedicated secret и входящие update IDs дедуплицируются в PostgreSQL.

При incident проверять:

- внешний webhook route;
- backend response;
- очередь Telegram;
- `telegram_updates.processed_at`;
- notification worker отдельно от inbound webhook.

Не смешивать «бот не получает updates» и «worker не может отправить сообщения»: это два независимых пути.

## 13. Retention

Maintenance worker удаляет только технические старые records согласно config, например:

- expired/revoked auth sessions;
- processed old Telegram updates;
- terminal notification outbox;
- expired decision callbacks.

Он не получает право удалять Warehouse journal, Procurement history или projections.

Retention выполняется bounded batches под advisory lock.

## 14. Backup readiness

Read-only check:

```bash
python3 ops/backup/check_status.py
```

Exit:

- 0 — ready;
- 1 — unhealthy/stale;
- 2 — usage error.

Status должен учитывать age recovery point и факт неуспешной последней попытки.

Наличие старого dump-файла само по себе не означает готовность к восстановлению.

## 15. Backup content

Successful backup state должен связывать:

- started/verified timestamps;
- clean checkout SHA;
- runtime provenance;
- database/Alembic metadata;
- dump size;
- dump SHA-256;
- S3 object key;
- dump VersionId;
- manifest VersionId.

Удалённая версия объекта важнее mutable «последнего имени».

## 16. Recovery rehearsal

Для проверки backup использовать только [RECOVERY_RUNBOOK.md](RECOVERY_RUNBOOK.md).

Rehearsal не должен:

- останавливать production Compose;
- использовать production database volume;
- менять mutation gate;
- подменять live containers.

## 17. Incident triage

### UI недоступен

Порядок:

1. DNS/TLS;
2. host Nginx;
3. Unix socket;
4. web `/healthz`;
5. backend live;
6. backend ready;
7. container state/logs.

### Ready = 503

Проверить:

1. PostgreSQL connectivity;
2. Alembic head;
3. critical trigger/function contract;
4. runtime role access к readiness query.

Не обходить readiness ручным снятием checks.

### Складская ошибка

Проверить:

1. mutation flag;
2. user capability/access;
3. movement payload/idempotency key;
4. stock/custody;
5. DB conflict SQLSTATE;
6. zero-drift reconciliation.

### Уведомления

Разделить:

- enqueue issue;
- worker claim issue;
- gateway/provider issue;
- stale/retry/dead issue.

## 18. Repository data policy

`REPOSITORY_VISIBILITY_CURRENT=public`.

В публичном Git не хранить **private/runtime-only production identifiers**, real inventory data, dumps и credentials.

**Public service identifiers** допустимы, если являются публичной частью архитектуры. Публичный application URL: `https://app.spik-inventory.ru`.

## 19. Branch hygiene

Рабочие ветки не являются эксплуатационным архивом. После merge/acceptance merged topic branches удаляются по обычной Git-политике.

История технических решений остаётся в Git history и current audit findings, а не в отдельных Markdown journals.
