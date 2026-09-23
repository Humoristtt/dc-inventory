# Эксплуатация Spikatel Inventory

Этот документ — рабочая карта сопровождения: какие сервисы ожидаются, как проверить их состояние и когда остановить опасную операцию. Пошаговый выпуск выполняется только по [DEPLOYMENT.md](DEPLOYMENT.md), изолированное восстановление — по [RECOVERY_RUNBOOK.md](RECOVERY_RUNBOOK.md), правила склада — по [WAREHOUSE_DOMAIN.md](WAREHOUSE_DOMAIN.md). Записи ниже **не означают**, что сервер проверен в момент чтения файла.

Актуализация документа: 19.09.2026. Последняя документированная production-проверка checkout/runtime `6d9bafef494f910b9bd1ebea7c5b7cf45f853742`, Alembic `c3d4e5f6a7b8`; source head `b0c1d2e3f4a5` относится к более новой ветке, а не к запущенной БД. Перед CP-16 повторно сверить все значения и конфигурацию на VM.

```text
ALEMBIC_HEAD=c3d4e5f6a7b8
SOURCE_ALEMBIC_HEAD=b0c1d2e3f4a5
RBAC_CUTOVER=PASS
PROCUREMENT_DEPLOYMENT=PASS
REAL_INVENTORY_MUTATIONS_ENABLED=false
```

## 1. Граница работы с production

VM не является development environment. Изменения runtime требуют approved SHA, CI/review, immutable images, verified off-VM backup, maintenance plan, критерии отката и явное разрешение. Source-only синхронизация docs/host-side `ops/` не запускает контейнеры и допускается без rebuild **только** при неизменных Docker build contexts/application runtime source; host scripts проверяем отдельно. Не принимать Git HEAD за фактическую версию запущенного образа.

Критичный открытый пункт CP-07: последний подтверждённый Tunnel origin — `http://localhost:8080`. Новый web image с изменённой моделью TCP доверия нельзя разворачивать на старый Tunnel origin: разные клиенты могут делить один rate-limit bucket. Нужны согласованная миграция web/Tunnel, фактические UID/GID, защищённый host-каталог Unix-сокета и рабочий rollback. Исходный `compose.yaml` ещё не содержит готового bind mount сокета, поэтому локальный `nginx -t` не подтверждает production готовность. Полный план — [CP07_HTTP_SOCKET_MIGRATION.md](CP07_HTTP_SOCKET_MIGRATION.md).

## 2. Какие контейнеры и состояния ожидаем

| Компонент | Состояние после успешного выпуска | Что проверяем |
|---|---|---|
| PostgreSQL | `healthy`, постоянный volume | Readiness, Alembic head, доступ только из нужной Docker-сети. |
| `migrate` | exited `0` | Схема точно соответствует approved release. |
| `db-permissions` | exited `0` | Фактические права ролей и отсутствие активных legacy sessions после разрешённого cutover. |
| Backend | `healthy` | `/api/health/live` и `/api/health/ready`, настоящий image ID/revision, OWNER/auth. |
| Web/Nginx | `healthy` | `/healthz`, loopback/Unix ingress согласно текущему approved плану, заголовки и rate limit. |
| Telegram worker | Работает, heartbeat актуален | Outbox claim/retry, Gateway HTTPS, отсутствие прямого Bot API token у worker. |
| Maintenance worker | Работает, heartbeat актуален | Одна успешная bounded retention iteration. |
| Email worker | Необязателен | Только при утверждённом профиле `email` и `EMAIL_DELIVERY_ENABLED=true`. |

В текущем исходном Compose PostgreSQL и backend не имеют host-published ports; web публикует `127.0.0.1:${WEB_PORT:-8080}`. Проверить фактические порты после выпуска. `/healthz`, `/api/health/live`, `/api/health/ready` должны отвечать HTTP 200 в здоровом состоянии. При недоступной БД `live` остаётся доступным (200), `ready` возвращает 503; после восстановления БД `ready` должен вернуться к 200 без рестарта backend. Нельзя считать зелёный `/healthz` доказательством корректности БД или outbox.

Сервисные Docker image revisions проверяем непосредственно по immutable image IDs и label `org.opencontainers.image.revision`; сравниваем с approved release manifest, а не только со строкой Git HEAD на VM. Исторический rollback image не является текущим runtime только потому, что его tag остался в Docker daemon.

## 3. PostgreSQL identities и права

В текущем runtime-контракте пять отдельных login identities: owner/migrator (`POSTGRES_USER`), backend, Telegram worker, optional email worker и maintenance. Owner credentials не передаются обычным сервисам. Backend не получает broad UPDATE/DELETE для immutable warehouse journal; изменение `telegram_updates` ограничено необходимым processed state; notification payload защищён от произвольного редактирования. Telegram и email workers не должны иметь взаимных outbox и складских привилегий. Maintenance ограничен сроками/объёмом удаления технических данных, не затрагивает immutable складской журнал.

`db-permissions` применяет SQL через `psql -X --single-transaction -v ON_ERROR_STOP=1`. При неудаче SQL должна откатиться выдача прав. Legacy-роль (`POSTGRES_LEGACY_WORKER_USER`, фактическое прежнее имя сверить отдельно) получает NOLOGIN/REVOKE **внутри транзакции**. `pg_terminate_backend()` завершает её прежние сессии **только после COMMIT**; это необратимый побочный эффект, который нельзя компенсировать SQL rollback. Проверка миграции/прав входит в утверждённый deployment, а не в ежедневную диагностику «на всякий случай».

## 4. Безопасность host и доступ

Последний исторически принятый host baseline нужно измерить повторно перед выпуском:

- UFW active;
- входящие соединения по умолчанию запрещены, исходящие разрешены, SSH `22/tcp` ограничен утверждёнными адресами;
- `PermitRootLogin no`;
- `PasswordAuthentication no`;
- `PubkeyAuthentication yes`;
- `X11Forwarding no`;
- `GatewayPorts no`;
- `AllowTcpForwarding yes` сохраняется для контролируемых административных SSH tunnels.

Это список требований/последних принятых настроек, а не результат нового чтения `sshd_config` и UFW. Не менять SSH/UFW без плана сохранения доступа. Loopback-only Docker ports обязательны независимо от состояния firewall.

По последнему документированному состоянию репозиторий публичный: `REPOSITORY_VISIBILITY_CURRENT=public`. В нём не должно быть `.env`, ключей, дампов, real inventory datasets, workbook contents и private/runtime-only идентификаторов. Public service identifiers, включая `https://app.spik-inventory.ru` и публичный support username, допустимы по назначению. `main` защищён required CI; merged topic branches удаляются после acceptance. Изменять видимость репозитория — отдельное security/operational решение, не часть технической чистки Markdown.

## 5. Telegram: вход и отправка

Входящий путь: Telegram → Cloudflare/Tunnel → Nginx → FastAPI webhook → PostgreSQL dedupe входящего update. Исходящий путь: транзакционный notification outbox → Telegram worker → HTTPS Cloudflare Worker Gateway → Telegram Bot API. Production VM не требует прямого выхода к `api.telegram.org:443`; worker не получает bot token. Для Gateway установлен секрет и разрешённый набор методов; потеря доступности Gateway не откатывает уже зафиксированное складское или закупочное действие.

После изменений runtime проверить настоящим Telegram клиентом `/start`: входящее сообщение удаляется best-effort, новое брендированное приветствие отправляется как `sendPhoto` с caption и WebApp button, публичный `/telegram/start-welcome.png` доступен. Проверить request → ADMIN notification → approve/reject → user notification → APPROVED login, включая фактические роли. Локальный Playwright с синтетически подписанным `initData` **не** заменяет CP-17 real Telegram acceptance.

Принятый пользовательский контракт: Telegram/mobile shell использует expand/viewport APIs; desktop-capable runtime автоматически запрашивает fullscreen там, где Telegram Desktop это поддерживает. Кнопка fullscreen находится в общей панели заголовка; Escape сначала закрывает `[data-escape-dismiss]`, затем fullscreen. Вопрос первого клика WebView после fullscreen исторически исследован в [FRONTEND_PERFORMANCE.md](FRONTEND_PERFORMANCE.md); не вводим автоматическое повторение пользовательского действия.

Telegram и Microsoft Graph email доставляются **at-least-once**, а не exactly-once. Dedupe key предотвращает дублирование outbox intent; при потере ответа внешнего провайдера сообщение/письмо может повториться. После исчерпания лимита попыток запись становится `DEAD`, а повторная постановка регулируется отдельной процедурой. Email по умолчанию выключен (`EMAIL_DELIVERY_ENABLED=false`); реальные Graph secrets, профиль `email` и live delivery acceptance ещё открыты в CP-08.

## 6. Retention и контроль данных

Defaults исходного кода: auth sessions — 7 дней; обработанные Telegram updates — 30 дней; terminal notification/email outbox — 90 дней; access callbacks — 30 дней. Размер batch — 1000, интервал maintenance — 3600 секунд. Worker использует PostgreSQL advisory transaction lock для одиночного выполнения. Immutable Warehouse journal не входит в техническое удаление.

`backend/scripts/reconcile_inventory_projections.sql` пересчитывает stock и custody **только для чтения** по immutable журналу. После миграций склада, восстановления, рискованного обслуживания или сообщения о несоответствии запускать сверку из совместимого runtime-контекста. Нормальный результат — ноль строк. При drift остановить опасные мутации, зафиксировать evidence/backup и выяснить причину; автоматического пересоздания остатков нет.

## 7. S3 backup и восстановление

Stage15A automated off-VM backup и исторический Stage15B isolated restore были приняты, но не заменяют свежую проверку текущего backup перед новым cutover. По последнему документированному состоянию provider — StorageGRID, endpoint `https://s3-msk-1.cloudstack.ru`, bucket `dc-inventory-prod-backups`, prefix `postgres/`. Object Lock GOVERNANCE — 7 дней; lifecycle текущих версий — 30 дней, нетекущих — 1 день. У backup identity нет DeleteObject, обхода retention и права менять lifecycle. Это **исторические сведения о конфигурации**, а не проверка S3 прямо сейчас.

Backup timer ежедневно в 02:30 Europe/Moscow с `Persistent=true`, state хранится в `/var/lib/dc-inventory-backup`. Постоянно накапливать локальные дампы на VM запрещено. Используются `ops/backup/dc-inventory-backup-s3`, `ops/backup/s3_stage15.py` и штатные systemd units. После неуспешного backup проверять код выхода, journal, last-success/last-failure state и совпадение remote artifact/checksum; не объявлять успех только по факту запуска timer.

CP-11 локально усилил manifest validation (schema, hash, size, runtime provenance), очистку только своих контейнеров, изоляцию credentials и отзыв восстановленных auth sessions. Настоящий повторный S3 rehearsal после CP-11 и восстановление утверждённой конфигурации Cloudflare/Telegram/Graph **ещё не выполнены**. Restore использует точный backend image и соответствующий его схеме reconciliation SQL, не монтирует production volume и не запускает старые активные сессии. Процедура и критерии ABORT — [RECOVERY_RUNBOOK.md](RECOVERY_RUNBOOK.md).

## 8. Initial production inventory bootstrap — accepted

```text
INITIAL_PRODUCTION_BOOTSTRAP=PASS
POST_IMPORT_RECONCILIATION=ZERO_DRIFT
POST_IMPORT_BACKUP=PASS
TELEGRAM_VISUAL_ACCEPTANCE=PASS
INITIAL_PRODUCTION_BOOTSTRAP=DO_NOT_RERUN
REAL_INVENTORY_MUTATIONS_ENABLED=false
```

Внешний операторский workbook прошёл проверку, защищённый one-shot bootstrap создал локацию и opening RECEIPT. Были проверены counts/quantity, zero drift, health, off-VM backup и реальный Telegram display. Сами workbook/data identifiers не публикуются. Повторный initial bootstrap запрещён. Обычные Warehouse mutation API требуют отдельного go-live решения, а не запуска уже выполненного импортного CLI.

## 9. Порядок реакции на неисправность

Сначала установить точный контур и изменение: baseline image/HEAD, Alembic, health, workers и время последнего успешного backup. При проблемах авторизации проверить серверную сессию и роли; при сообщении об остатке — read-only reconciliation и журнал; при `DEAD` — lease/attempts и состояние внешнего Gateway; при ошибке готовности БД — PostgreSQL и сети. Не исправлять проблему изменением production `.env`, прямым SQL UPDATE проекций или открытием mutation gate без отдельного решения.

Если необходимы миграции, смена Cloudflare origin, ротация OWNER или восстановление, остановить рутинную диагностику и перейти к соответствующему согласованному runbook. CP-07–12 остаются открытыми до фактических production evidence, независимо от локальных тестов и этой документации. Статусы и доказательства — в [AUDIT_0_12_REMEDIATION.md](AUDIT_0_12_REMEDIATION.md).
