# Deployment

Deployment меняет production и выполняется только после отдельного разрешения. Этот runbook не содержит «принятого прошлого baseline»: перед каждым выпуском live state измеряется заново.

## 1. Preconditions

До изменения production должны быть известны:

- approved full Git SHA;
- зелёный required CI;
- один ожидаемый Alembic head;
- compatible migration/application plan;
- свежая verified off-VM backup;
- maintenance window;
- rollback или forward-fix strategy;
- ответственный оператор;
- критерии немедленной остановки.

Проверить, что production env проходит:

```bash
python3 ops/validate_env_file.py --production /path/to/production.env
```

Секреты не печатать в терминальный лог/чат.

## 2. Release artifact

Release builder:

```bash
python3 ops/release/build_release.py   --env-file /path/to/production.env   --output /restricted/path/release-<sha>
```

Builder:

1. требует clean Git checkout;
2. берёт точный `git rev-parse HEAD`;
3. требует full 40-char SHA;
4. запрещает повторное использование существующих release tags;
5. проверяет production env;
6. строит backend/web/postgres;
7. сверяет OCI `org.opencontainers.image.revision`;
8. фиксирует immutable image IDs;
9. публикует `release.json` и `release.env` только после успешной проверки.

Builder **не deploy-ит**.

## 3. Runtime identities

Используются разные PostgreSQL credentials:

- owner — только migrate/db-permissions;
- application runtime;
- Telegram worker;
- email worker;
- maintenance worker;
- optional legacy worker name только для revoke/NOLOGIN cleanup.

Backend/workers не должны получать owner URL.

## 4. Production ingress

Для production user traffic применяется:

```text
public HTTPS
→ host Nginx
→ /var/lib/dc-inventory-ingress/ingress.sock
→ web Nginx
→ backend
```

Compose запускается с `compose.ingress-unix.yaml`. Этот override:

- удаляет web host TCP port;
- удаляет `ingress_net`;
- bind-mounts заранее подготовленный host directory в `/run/dc-inventory`.

Host ingress configuration устанавливается отдельным скриптом:

```bash
sudo ops/host_ingress/apply.sh --confirm=APPLY_HOST_DIRECT_INGRESS
```

После этого обязательна read-only проверка:

```bash
sudo python3 ops/host_ingress/verify.py
```

Не переключать ingress одновременно с unrelated application release без причины.

## 5. Controlled cutover

Общий порядок:

1. зафиксировать live checkout, runtime image IDs/revisions и DB head;
2. подтвердить свежую backup;
3. подготовить approved release artifact;
4. если migration несовместима со старым runtime — остановить старые app/workers до schema change;
5. выполнить `migrate` из approved backend image;
6. выполнить `db-permissions`;
7. убедиться, что one-shot jobs завершились с code 0;
8. запустить backend/web/Telegram/maintenance на approved images;
9. email worker запускать только если email явно включён;
10. проверить health/readiness;
11. собрать runtime provenance;
12. сравнить release и runtime;
13. выполнить domain reconciliation/smoke;
14. сделать post-deploy backup.

Не выполнять destructive downgrade только ради быстрого rollback. Если старый application несовместим с новой schema, нужен совместимый forward-fix или проверенное восстановление application+database как пары.

## 6. Migrations

One-shot service `migrate` выполняет:

```text
alembic upgrade head
```

Migration timeouts отделены от runtime request timeouts.

После migration:

```text
db-permissions
```

применяет grants одной SQL-транзакцией. Legacy session termination выполняется только после успешного commit grants.

## 7. Mutation flags

Production deployment сам по себе не включает business mutations.

Default:

```text
REAL_INVENTORY_MUTATIONS_ENABLED=false
EMAIL_DELIVERY_ENABLED=false
```

Любое изменение этих значений — отдельное решение с собственным acceptance.

## 8. Release/runtime provenance

После запуска собрать фактический runtime provenance через:

```bash
python3 ops/backup/runtime_provenance.py   --root /path/to/checkout   --env-file /path/to/production.env   --output /restricted/path/runtime-provenance.json   --production-checkout-sha <approved-full-sha>
```

Затем:

```bash
python3 ops/release/verify_release_runtime.py   --release-manifest /restricted/path/release.json   --runtime-provenance /restricted/path/runtime-provenance.json
```

Обязательный результат:

```text
RELEASE_RUNTIME_MATCH=PASS
```

Verifier требует:

- checkout SHA == release SHA;
- backend/web/postgres image IDs == approved IDs;
- image revision labels совпадают;
- Telegram/maintenance worker == backend image;
- email worker либо disabled, либо тот же backend image.

При mismatch не «исправлять» manifest под live runtime.

## 9. Health

После запуска:

```text
GET /healthz
GET /api/health/live
GET /api/health/ready
```

Ожидание:

- web health — 200/ok;
- live — 200 при живом process;
- ready — 200 только при совместимой/доступной DB;
- при DB/schema problem ready должен fail closed.

## 10. Network checks

Подтвердить фактически:

- PostgreSQL не имеет host-published port;
- backend не имеет host-published port;
- production web не имеет host TCP port;
- web имеет только app network + Unix socket mount;
- Telegram worker: db + egress, без app network;
- maintenance: только db network;
- backend: app + db, без egress.

## 11. Database role checks

Проверить effective grants, а не только SQL source:

- runtime schema CREATE = false;
- movements/movement_lines UPDATE/DELETE = false;
- stock/custody direct DML = false;
- projection refresh function EXECUTE = true;
- outbox/identity UPDATE columns соответствуют allowlist;
- workers не видят чужие domain/outbox tables.

CI содержит reference matrix, но production role names проверяются live.

## 12. Domain verification

После schema/application change:

- Catalog read;
- auth/OWNER login;
- Warehouse reconciliation — zero drift;
- Procurement read/flow, если change его затронул;
- worker heartbeat;
- Telegram smoke, если менялась Telegram boundary;
- email smoke только если email был явно включён.

Reconciliation script:

```text
backend/scripts/reconcile_inventory_projections.sql
```

Он read-only и должен возвращать ноль drift rows.

## 13. Recovery OWNER

Обычный API не меняет recovery OWNER.

Rotation выполняется отдельной maintenance-процедурой из exact approved backend image. Перед ней нужны backup, остановка competing identity mutations и проверка target identity/custody.

CLI находится в:

```text
python -m app.bootstrap.recovery_owner_rotation
```

Параметры брать из `--help` текущего image; не копировать старые идентификаторы из документации.

## 14. Initial inventory bootstrap

`python -m app.bootstrap.production_inventory` — one-shot bootstrap tool, а не штатный способ изменения склада.

Повторный запуск на непустом Warehouse запрещён его guards. Новые складские данные вводятся через normal domain operations при отдельно включённом mutation gate.

## 15. Post-deploy backup

После успешной приёмки запустить/подтвердить штатную off-VM backup и проверить status:

```bash
python3 ops/backup/check_status.py
```

Backup должен быть fresh, latest attempt — success.

## 16. Что не является deployment

Не являются deployment:

- Git push;
- merge документации;
- source-only checkout update;
- успешный CI;
- локальная сборка.

Production считается изменённым только после фактического изменения runtime/schema/config/ingress/external service.
