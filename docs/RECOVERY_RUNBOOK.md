# Recovery runbook

Recovery проверяется сначала в изолированном rehearsal. Запуск production cutover — отдельное решение после успешного rehearsal и отдельного подтверждения.

## 1. Цель

Доказать, что выбранная off-VM backup:

- действительно скачивается по зафиксированным version IDs;
- соответствует manifest;
- проходит SHA-256/size verification;
- восстанавливается в чистый PostgreSQL;
- имеет ожидаемый Alembic head;
- совместима с точными backend/web runtime artifacts;
- даёт zero-drift Warehouse reconciliation;
- не требует изменения работающего production runtime.

## 2. Предварительные условия

Перед rehearsal:

- production health/live и ready успешны;
- production checkout clean;
- штатный backup state readable и `success`;
- mutation gate production закрыт;
- exact backup object versions доступны;
- Docker работает;
- локально доступны или могут быть получены exact images из manifest.

Не запускать rehearsal при неизвестном состоянии production.

## 3. Guarded command-level rehearsal

Canonical script:

```text
ops/recovery/rehearse_restore.sh
```

Запуск на production host выполняется только как read-only rehearsal относительно live application:

```bash
sudo -n bash ops/recovery/rehearse_restore.sh
```

Script сам создаёт отдельные временные:

- work directory;
- internal Docker network;
- Docker volume;
- PostgreSQL container;
- application compatibility container.

Cleanup выполняется через trap и удаляет только resources с собственным restore run prefix.

## 4. Что выбирается из backup state

`last-success.json` определяет manifest object key.

Далее необходимо **из manifest получить immutable backend/web image ids** и соответствующие source revisions.

Manifest и dump скачиваются по конкретным S3 VersionId, а не по mutable latest object.

Проверяются:

- manifest schema;
- object keys/prefix;
- dump VersionId;
- dump content length;
- dump SHA-256;
- checkout/runtime metadata;
- Alembic metadata.

## 5. Exact runtime artifacts

Для проверки application compatibility необходимо **запустить точный доступный backend image**, указанный в manifest, а не пересобирать image из сегодняшнего checkout.

Также проверяется exact web image metadata.

Если exact artifact недоступен, rehearsal считается неуспешным. Нельзя подменять его новым image с тем же human-readable tag.

## 6. Database restore

Изолированный PostgreSQL:

1. создаётся на отдельном internal network;
2. использует отдельный disposable volume;
3. получает случайный rehearsal password;
4. получает dump через `pg_restore`;
5. перед restore dump проверяется через `pg_restore --list`;
6. после restore сверяется Alembic head.

Production database/volume не используется.

## 7. Projection reconciliation

Reconciliation берётся **из exact backend image**:

```text
/app/scripts/reconcile_inventory_projections.sql
```

Это важно: source checkout может уже отличаться от приложения, которому соответствует backup.

Ожидание:

```text
RESTORE_RECONCILIATION=ZERO_DRIFT
```

Любая строка drift блокирует cutover.

## 8. Application compatibility

Exact backend image запускается против restored disposable DB с isolated placeholder runtime config и закрытым mutation gate.

Проверяются application compatibility и health semantics без внешней бизнес-мутации.

Email runtime определяется из manifest: enabled/disabled/legacy state должен быть обработан явно.

## 9. Production unchanged invariant

Script фиксирует production container IDs до rehearsal и сравнивает их после.

Недопустимы:

- `docker compose down -v`;
- остановка production PostgreSQL;
- замена production image;
- включение `REAL_INVENTORY_MUTATIONS_ENABLED=true`;
- переключение ingress;
- изменение Telegram webhook;
- запись в production DB.

Успешный rehearsal должен завершиться маркером, подтверждающим неизменность production runtime.

## 10. Критерии PASS

Минимально:

```text
PRODUCTION_PRECHECK=PASS
RESTORE_DOWNLOAD_VERIFICATION=PASS
RESTORE_MANIFEST_CHECKOUT_METADATA=PASS
EXACT_RUNTIME_ARTIFACTS_LOCAL=PASS
RESTORE_ALEMBIC=PASS
RESTORE_RECONCILIATION=ZERO_DRIFT
RESTORE_APP_COMPATIBILITY=PASS
ISOLATED_RESTORE=PASS
PRODUCTION_RUNTIME_UNCHANGED=PASS
```

Если любой шаг fail — backup не считается принятой точкой восстановления для cutover.

## 11. Production cutover boundary

Rehearsal **не выполняет production cutover**.

Перед реальным восстановлением отдельно утверждаются:

- выбранный recovery point;
- допустимый RPO;
- точные database dump/manifest version IDs;
- compatible backend/web/postgres artifacts;
- downtime window;
- порядок остановки writers;
- DNS/ingress strategy;
- post-restore verification;
- rollback/abort criteria.

Нельзя автоматически брать «самый новый» объект, если operator выбрал другой recovery point.

## 12. Общий порядок production restore

Только после отдельного разрешения:

1. остановить все writers;
2. зафиксировать pre-cutover state/provenance;
3. при возможности сделать дополнительную backup текущего состояния;
4. развернуть чистый target PostgreSQL/volume;
5. восстановить выбранный versioned dump;
6. проверить DB/Alembic/schema;
7. выполнить zero-drift reconciliation exact backend image;
8. запустить compatible app runtime с mutations disabled;
9. проверить auth/read-only flows;
10. переключить ingress только после успешной проверки;
11. отдельно принять решение о возврате mutations;
12. сделать новую verified backup восстановленного состояния.

Не восстанавливать старую DB под несовместимый новый application image.

## 13. После восстановления

Проверить:

- `/healthz`;
- `/api/health/live`;
- `/api/health/ready`;
- OWNER/auth flow;
- runtime provenance;
- DB role grants;
- Warehouse reconciliation;
- Procurement final-movement consistency;
- workers/heartbeat;
- новую off-VM backup.

External delivery включать только согласно фактическому pre-restore configuration и отдельному acceptance.

## 14. Запреты

Нельзя считать восстановление доказанным по одному `pg_restore` exit code.

Обязательны одновременно:

- cryptographic/object identity;
- schema identity;
- application artifact identity;
- domain reconciliation;
- runtime isolation;
- post-restore health.
