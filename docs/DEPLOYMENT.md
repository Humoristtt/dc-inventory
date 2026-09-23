# Выпуск Spikatel Inventory: артефакты, миграции и проверка

Документ определяет порядок **согласованного** выпуска приложения, а не разрешает выполнять его автоматически. Разработка выполняется на Mac, утверждённый код поступает через GitHub, production VM использует read-only Deploy Key. Push в remediation-ветку, обновление документации, merge или `git pull` **не** обновляют уже работающие Docker images, PostgreSQL и Cloudflare Tunnel. За фактическим эксплуатационным состоянием обращаемся к [OPERATIONS.md](OPERATIONS.md), за восстановлением — к [docs/RECOVERY_RUNBOOK.md](RECOVERY_RUNBOOK.md), за специальным переходом ingress — к [CP07_HTTP_SOCKET_MIGRATION.md](CP07_HTTP_SOCKET_MIGRATION.md).

## 1. Исходное состояние и разрешение

Последняя документированная production-проверка: checkout/runtime `6d9bafef494f910b9bd1ebea7c5b7cf45f853742`, Alembic `c3d4e5f6a7b8`. Это **историческое evidence**, не сегодняшняя проверка. Текущий source migration head: `a9c0d1e2f3a4`. Прежде чем утверждать план, оператор должен заново проверить реальный Git HEAD на VM, PostgreSQL Alembic head, image IDs/revisions, Compose, Tunnel origin, host-права, сервисы и backup.

Warehouse Domain V2 и первоначальный импорт ранее приняты; initial bootstrap повторно не запускается. По последнему production evidence обычные складские мутации закрыты:

```text
REAL_INVENTORY_MUTATIONS_ENABLED=false
EMAIL_DELIVERY_ENABLED=false
```

Изменение этих флагов требует самостоятельного решения и acceptance. CP-07–12 содержат локально исправленные, но ещё не принятые в production части. CP-14 завершил изолированную full-stack приёмку, CP-15 — предрелизный аудит, CP-16 deployment, CP-17 реальный Telegram smoke. Закрытый локальный checkpoint не даёт права считать production обновлённым.

**Перед изменением production** получить approved immutable SHA, результат required CI/review, подтверждённую совместимость схемы и артефактов, свежую verified off-VM backup, maintenance window, план отката или forward-fix, перечень ответственных и критерии немедленной остановки. Без этих условий никакие команды ниже не выполняются на VM.

## 2. Контейнеры, сети и учётные записи

`compose.yaml` описывает PostgreSQL, одноразовые `migrate` и `db-permissions`, FastAPI backend, Nginx web, Telegram worker, maintenance worker и необязательный email worker (`profiles: ["email"]`). Backend, workers и PostgreSQL работают в разделённых Docker-сетях. PostgreSQL volume постоянный; host-порт базы и backend не публикуются. По текущему Compose web слушает на host только `127.0.0.1:${WEB_PORT:-8080}`; текущий Tunnel по последней проверке направлен на `http://localhost:8080`. Это **прежняя конфигурация**, а не доказательство, что Unix-вход готов в production.

Сервисы используют read-only root filesystem, временные `/tmp`, `cap_drop: ALL`, `no-new-privileges`, ограничения CPU/RAM/PID и ограниченные логи Docker. Backend image запускает приложение от UID 10001; фактический UID/GID Nginx и systemd `cloudflared` обязательно измеряются перед CP-07. `/healthz` проверяет web, `/api/health/live` — приложение, `/api/health/ready` — доступность БД и readiness.

Пять независимых PostgreSQL identities:

| Назначение | Параметры production `.env` |
|---|---|
| Owner/migrator | `POSTGRES_USER`, `POSTGRES_PASSWORD` |
| Backend runtime | `POSTGRES_RUNTIME_USER`, `POSTGRES_RUNTIME_PASSWORD` |
| Telegram worker | `POSTGRES_TELEGRAM_WORKER_USER`, `POSTGRES_TELEGRAM_WORKER_PASSWORD` |
| Опциональный email worker | `POSTGRES_EMAIL_WORKER_USER`, `POSTGRES_EMAIL_WORKER_PASSWORD` |
| Maintenance | `POSTGRES_MAINTENANCE_USER`, `POSTGRES_MAINTENANCE_PASSWORD` |

Роли runtime не используют owner credentials. Контейнеры получают внутренний URL вида `postgresql+asyncpg://USER:PASSWORD@postgres:5432/DATABASE`; фактические значения, токены и секреты **не** записываются в Git, команды в журнале или ответы чат-бота. Legacy-роль задаётся отдельно через `POSTGRES_LEGACY_WORKER_USER` (default `dc_inventory_worker`), если её фактическое имя не совпадает с default, необходимо уточнить до cutover.

После успешного Alembic `db-permissions` запускает `psql -X --single-transaction -v ON_ERROR_STOP=1` и выдаёт изолированные права. SQL-ошибка откатывает изменения привилегий; только **после успешного COMMIT** отдельный запрос выполняет `pg_terminate_backend()` для legacy sessions. Завершённые соединения не восстанавливаются SQL rollback. Backend/workers зависят от успешного выхода permissions service; отсутствие legacy-роли на чистом сервере — допустимый сценарий. Не запускайте старые workers с широкой общей ролью после cutover.

## 3. Release artifacts и provenance

Внешние container images закреплены тегом и immutable manifest digest, GitHub Actions — полным commit SHA. `APP_REVISION` должен отражать SHA исходников, использованных при сборке. OCI label `org.opencontainers.image.revision` берём из **самого Docker image**, а не доверяем изменяемой метке контейнера.

Штатный builder:

```text
ops/release/build_release.py --env-file <approved-env-file> --output <new-output-directory>
```

Он требует чистый checkout, полный Git SHA, свободные release tags и валидные immutable IDs/revision labels backend/web/postgres; публикует `release.json` и `release.env` только после успешной проверки всех компонентов. При ошибке незавершённый output directory удаляется, но созданные Docker tags могут остаться: сначала установить их владельца, **не** удалять чужие образы автоматически. Builder ничего не развёртывает.

### Обязательная сверка релиза при CP-16

После отдельно разрешённого развёртывания собрать фактический runtime provenance через `ops/backup/runtime_provenance.py`. До приёмки выполнить `python3 ops/release/verify_release_runtime.py --release-manifest APPROVED_RELEASE_JSON --runtime-provenance RESTRICTED_RUNTIME_JSON`.

Манифест `release.json` должен быть утверждён заранее и храниться независимо от работающих контейнеров. Обязательный результат — `RELEASE_RUNTIME_MATCH=PASS`: точные image ID и revisions backend/web/PostgreSQL, соответствие workers и checkout SHA. При несовпадении остановить приёмку; не пересобирать образы и не подменять манифест. Source-only синхронизация с другим checkout SHA требует отдельной проверки и разрешения: verifier не допускает это расхождение.

Альтернативная ручная сборка **в рамках утверждённого runtime release**, а не документационной синхронизации:

```bash
REVISION="$(git rev-parse HEAD)"
APP_REVISION="$REVISION" docker compose build backend postgres web
```

`ops/backup/runtime_provenance.py` проверяет соответствие заявленного checkout SHA реальному HEAD и читает immutable IDs/revisions фактически работающих images. Telegram/maintenance workers должны соответствовать backend image, email worker проверяется при включении. Допустимый source-only docs/host-side `ops/` sync может оставить image revision старее Git HEAD **только при доказанно неизменных Docker build contexts и application runtime source**; host-side `ops/` scripts проверяются отдельно. Такой sync не является deploy.

## 4. Отдельный обязательный gate CP-07: Tunnel и Unix

В исходном `frontend/nginx.conf` реализованы два входа: недоверенный TCP `:8080` без доверия входящему `CF-Connecting-IP`, и доверенный Unix `/run/dc-inventory/ingress.sock` с `set_real_ip_from unix:` и `real_ip_header CF-Connecting-IP`. На новом TCP входе реальные пользователи старого Tunnel могут разделить один per-client rate-limit bucket.

**Нельзя выпускать новый web image, оставляя production Tunnel на прежнем TCP-origin.** До change window нужно проверить поддержку Unix-origin установленной версией `cloudflared`, точные UID/GID, доступный только разрешённой группе host-каталог режима `0750`, bind mount и сетевую схему. Текущий исходный `compose.yaml` описывает web loopback port, но не содержит готового bind mount каталога сокета: перед production переходом необходимо отдельно подготовить и проверить фактическую конфигурацию доставки этого каталога в web-контейнер. Ни наличие Unix `listen` в Nginx, ни локальный `nginx -t` этого не доказывают.

Во время отдельного согласованного окна переключают **совместно** web image и Tunnel-origin, проверяют двух независимых клиентов, rate limits, внешний HTTPS, backend заголовки, доступ к сокету и Telegram. Откат возвращает **и** прежний web, **и** прежний Tunnel TCP-origin. Полные prerequisites и критерии отказа — в [CP07_HTTP_SOCKET_MIGRATION.md](CP07_HTTP_SOCKET_MIGRATION.md). Пока это не выполнено, CP-07 остаётся OPEN.

## 5. Telegram, Graph и секреты

Production backend требует `TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_USER_ID`, `NOTIFICATION_TELEGRAM_USER_ID`, `TELEGRAM_WEBHOOK_SECRET` и корректный HTTPS-origin `TELEGRAM_WEB_APP_URL` без path/query/fragment. `ADMIN_TELEGRAM_USER_ID` закрепляет единственного recovery OWNER; операционные уведомления направляются отдельному `NOTIFICATION_TELEGRAM_USER_ID`. Frontend bot token не получает.

Входящий webhook `/api/telegram/webhook` проверяет `X-Telegram-Bot-Api-Secret-Token`. Исходящие сообщения берёт из outbox Telegram worker и отправляет на HTTPS `TELEGRAM_GATEWAY_URL` с `TELEGRAM_GATEWAY_SECRET`; Bot API token хранится у доверенного Cloudflare Worker и у backend для проверки initData, но **не** у отправляющего worker. Gateway ограничивает методы `sendMessage`, `sendPhoto`, `deleteMessage`, `editMessageText`, `editMessageReplyMarkup`, `answerCallbackQuery`. При смене bot token требуется согласованное обновление секретов backend/Gateway и проверка входящих/исходящих операций. Недоступный Gateway не откатывает уже совершённый складской COMMIT.

`EMAIL_DELIVERY_ENABLED=false` по умолчанию. Включение Microsoft Graph требует утверждённых tenant/client/sender секретов, отдельной DB role, профиля `email` и live acceptance. Ошибка внешней отправки не отменяет транзакцию закупки; при lost acknowledgement возможно повторное сообщение. Ни Telegram, ни email не дают exactly-once внешнего side effect.

## 6. Миграции и controlled cutover

1. Записать фактические source/runtime/image/database baselines и зависимости. Получить свежую проверенную backup и проверить доступность точного rollback artifact.
2. Если новая миграция несовместима со старым приложением, остановить старые web/backend/workers **до** изменения схемы, сохранив PostgreSQL healthy.
3. Из утверждённого release выполнить Alembic upgrade до ожидаемого единственного head. Migration timeout и lock timeout независимы от runtime defaults: `MIGRATION_STATEMENT_TIMEOUT_SECONDS=300`, `MIGRATION_LOCK_TIMEOUT_SECONDS=5`.
4. После миграции выполнить `db-permissions`; проверить фактические GRANT/REVOKE, legacy role и момент завершения соединений.
5. Запустить только новые совместимые runtime images, затем выполнить совместное переключение CP-07 по отдельному плану.
6. Подтвердить health, OWNER/login, outbox/worker heartbeat, фактические image IDs/revisions, разрешения, read-only reconciliation и реальный Telegram smoke. Записать результаты и новую backup.

Историческая RBAC migration `f8a9b0c1d2e3 → a1b2c3d4e5f6` уже была выполнена; её нельзя применять повторно или запускать pre-RBAC backend на новой схеме. Downgrade SFP и другие потенциально разрушительные откаты разрешены только при доказанном отсутствии новых несовместимых данных и прохождении migration guards. Если downgrade небезопасен, выбирать согласованный forward-fix или восстановление проверенной pre-cutover backup **вместе с совместимым приложением**, но не просто возвращать старый image поверх новой схемы.

## 7. Initial production inventory bootstrap

Первоначальный импорт был выполнен однократно 08.09.2026. CLI `python -m app.bootstrap.production_inventory` не является штатным API изменения склада. Он требовал `APP_ENV=production`, корректную Docker/PostgreSQL boundary, закрытый `REAL_INVENTORY_MUTATIONS_ENABLED=false`, явное подтверждение, внешний workbook с ожидаемыми SHA/counts, APPROVED ADMIN и пустой Warehouse domain. В одной транзакции создавались target StorageLocation и opening RECEIPT, затем проверялись количества и zero-drift до COMMIT.

**Не запускать CLI повторно** на наполненной production БД, не публиковать workbook, актёра или private inventory identifiers. Разрешение обычных мутаций требует отдельного operational go-live решения и не следует из исторической приёмки bootstrap.

## 8. Recovery OWNER — только отдельная процедура

Обычным API нельзя сменить OWNER. При необходимости запланировать отдельное maintenance окно, остановить runtime/workers, убедиться в healthy PostgreSQL, доступности verified off-VM backup, существовании целевой TelegramIdentity и отсутствии custody. Утверждённая команда выполняется из **точного целевого backend image**:

```bash
docker compose --env-file .env -f compose.yaml run --rm --no-deps backend \
  python -m app.bootstrap.recovery_owner_rotation \
  --current-telegram-user-id CURRENT_TELEGRAM_ID \
  --target-telegram-user-id TARGET_TELEGRAM_ID \
  --target-user-id TARGET_USER_UUID \
  --confirm ROTATE_RECOVERY_OWNER
```

CLI под PostgreSQL lock атомарно переводит прежнего OWNER в ADMIN, назначает нового OWNER, пишет immutable audit, отзывает обе sessions и проверяет singleton. **После COMMIT и до повторного запуска backend** заменить `ADMIN_TELEGRAM_USER_ID` в production `.env`, иначе recovery reconciliation fail-closed. Сама документация не даёт разрешения выполнять ротацию.

## 9. Проверка после выпуска

На утверждённом ingress проверить `/healthz`, `/api/health/live`, `/api/health/ready`: ожидается HTTP 200; при временно недоступном PostgreSQL live может оставаться 200, ready обязан возвращать 503. Проверить actual running `postgres/backend/web`, Telegram/maintenance workers и optional email; одноразовые `migrate`/`db-permissions` должны завершиться с кодом 0. Убедиться, что backend `8000` и PostgreSQL `5432` не опубликованы на host, web доступен только через ожидаемый origin и права Unix каталога корректны.

Сверить OCI image revisions и конфигурацию, OWNER/access flow, heartbeat, успешную retention iteration. После изменений Telegram проверить реальный `/start`: вход через webhook, best-effort удаление старого сообщения, branded `sendPhoto`/caption и WebApp-кнопку, доступность `/telegram/start-welcome.png`, request → approve/reject → уведомление → вход. После миграций склада выполнить read-only `backend/scripts/reconcile_inventory_projections.sql` и требовать **ноль строк**. Сохранить post-deploy backup, результаты и причины возможных отклонений.

Реальное восстановление из production S3 после CP-11 требует отдельного rehearsal по [docs/RECOVERY_RUNBOOK.md](RECOVERY_RUNBOOK.md); исторический Stage15B PASS не заменяет текущую проверку. Ни один шаг выпуска не выполняем только потому, что редактировали Markdown.
