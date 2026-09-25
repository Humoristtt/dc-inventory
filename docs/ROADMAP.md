# Состояние проекта и порядок дальнейших работ

Документ фиксирует последовательность работ, а не заменяет технические требования или журнал проверок. Дата сверки: 25.09.2026. Текущий `main` и принятый production release — `593ddec0c9100b0df2eafe4f324c7bb600d75cba`. Для описания устройства системы используем [архитектуру](ARCHITECTURE.md), для технических подробностей исправлений — [журнал CP-00–18](AUDIT_0_12_REMEDIATION.md), для истории предыдущих выпусков — [HISTORY.md](HISTORY.md).

## 1. Разделяем исходники и работающую систему

| Контур | Подтверждённое состояние | Что означает |
|---|---|---|
| Исходный код | `main` = `593ddec0c9100b0df2eafe4f324c7bb600d75cba`; source Alembic head `b0c1d2e3f4a5` | Документационные изменения после release не меняют runtime сами по себе. |
| Production | Checkout/runtime `593ddec0c9100b0df2eafe4f324c7bb600d75cba`, Alembic `b0c1d2e3f4a5`; provenance/roles/reconciliation/ingress/readiness/backup PASS | Это подтверждённый baseline 25.09.2026, но не замена live-проверке перед будущим change. |
| Складские изменения | `REAL_INVENTORY_MUTATIONS_ENABLED=false` по последнему production evidence | Обычные мутации закрыты. Ранее выполненный одноразовый импорт не означал снятие этой защиты. |

Git push и изменение документации не меняют запущенные контейнеры. CP-16 и CP-17 уже завершены для указанного release; любой следующий production change снова требует отдельного разрешённого окна, свежей backup, rollback/forward-fix плана и проверки конфигурации.

## 2. Реализованная основа

- [x] Telegram Mini App, React/TypeScript, FastAPI, PostgreSQL, Docker Compose, Cloudflare Tunnel и Telegram Gateway.
- [x] Проверка Telegram `initData` сервером, HttpOnly-сессии, lifecycle заявок на доступ и capability-based RBAC.
- [x] Роли `ENGINEER`, `SENIOR_ENGINEER`, `MANAGER`, `ADMIN`, `OWNER` в исходниках и последнем подтверждённом production baseline.
- [x] Production RBAC maintenance cutover.
- [x] PostgreSQL outbox для Telegram и опционального Microsoft Graph email; внешняя доставка at-least-once.
- [x] Разделённые учётные записи PostgreSQL для миграций, backend, Telegram, email и maintenance в конфигурации текущего исходного кода.

Роли, разрешения и жизненный цикл закупки определены в [RBAC_PROCUREMENT.md](RBAC_PROCUREMENT.md). Внешнюю доставку нельзя считать exactly-once при потере ответа шлюза.

## 3. Каталог и склад

- [x] Каталог с фиксированной иерархией family → leaf и версионированными схемами атрибутов; поиск, фильтры, фасеты и отображение остатков по локациям.
- [x] Количественный Warehouse Domain V2 без действующего учёта serial/WWN конкретных экземпляров.
- [x] `StockBalance = Item × StorageLocation × positive quantity`; `UserItemCustodyBalance = User × Item × positive quantity`.
- [x] Неизменяемый журнал RECEIPT, ISSUE, RETURN, TRANSFER, WRITE_OFF, CORRECTION, REVERSAL; атомарное обновление остатков и custody.
- [x] Идемпотентность движений, сериализация конфликтующих операций и read-only сверка проекций по журналу.
- [x] Защита итогового RECEIPT закупки от обычного складского CORRECTION/REVERSAL реализована в исходниках; новые DB-инварианты ещё требуют production cutover.

Warehouse Domain V2 развёрнут и принят ранее. Initial bootstrap завершён и повторно не запускается. Его результат подтверждался сверкой остатков и внешней резервной копией. Разрешение обычных складских операций — отдельное решение, не часть повторного импорта. Точные инварианты — [WAREHOUSE_DOMAIN.md](WAREHOUSE_DOMAIN.md), атрибуты каталога — [CATALOG_SCHEMA.md](CATALOG_SCHEMA.md).

## 4. Закупки и пользовательские сценарии

- [x] Закупки с неизменяемыми редакциями и событиями, назначением менеджера, циклом корректировок и расхождениями без изменения склада.
- [x] При финальной технической приёмке создаётся один Warehouse RECEIPT в общей транзакции с завершением закупки.
- [x] Локально проверены исправления идентичности закупочных позиций, пагинации, поиска и повторной отправки с постоянным `client_request_id`.
- [x] CP-14: изолированный браузерный сценарий с реальными HTTP API и PostgreSQL, подписанным синтетическим Telegram `initData`, проверкой RBAC, склада, закупок и reconciliation.
- [x] Реальная приёмка актуального выпуска через Telegram Mini App после CP-16 — PASS 25.09.2026.
- [ ] Включение и проверка Microsoft Graph email в production — только с утверждёнными секретами и отдельным профилем.

В рамках CP-14 зафиксированы backend `540 passed, 1 skipped`, frontend `150 passed`, Playwright `2 passed`. SFP downgrade safety относится к отдельному CI gate. Эти результаты относятся к локальному изолированному контуру, не к production.

## 5. Исправления Audit 0–12 и предрелизная работа

| Этап | Состояние | Следующее действие |
|---|---|---|
| CP-00–CP-06 | Закрытые локальные технические этапы по журналу | Не изменять без воспроизведённой регрессии. |
| CP-07 | CLOSED | Production ingress принят: direct user ingress через host Nginx/Unix socket; Tunnel выделен только под Telegram webhook. |
| CP-08 | PARTIAL | Telegram live delivery accepted; Microsoft Graph email остаётся выключенным и требует отдельной приёмки. |
| CP-09 | CLOSED | Production runtime roles/grants проверены; legacy LOGIN=false, active legacy sessions=0. |
| CP-10 | CLOSED | Immutable release/runtime provenance принят на production. |
| CP-11 | PARTIAL | Post-deploy off-VM backup PASS; отдельный real restore/rehearsal по runbook остаётся открытым. |
| CP-12 | OPEN | Финальная сопровождаемость и crosswalk перепроверяются в CP-18. |
| CP-13 | CLOSED — локальная проверка 20.09.2026 | 23 Markdown сверены; документационные контракты PASS. |
| CP-14 | CLOSED | Изолированная full-stack приёмка пройдена. |
| CP-15 | CLOSED | Предрелизные проверки завершены перед approved release. |
| CP-16 | CLOSED | Production release `593ddec...` принят 25.09.2026. |
| CP-17 | CLOSED | Real Telegram webhook/Mini App/auth/access acceptance PASS 25.09.2026. |
| CP-18 | OPEN — NEXT | Новый независимый аудит двенадцати разделов по итоговому коду и production evidence. |

В CP-15 выявлен и исправлен порядок проверки одноразовой PostgreSQL: проверка топологии и случайного маркера выполняется **до** Alembic. Коммит `38d1b19`; после исправления — два Playwright-теста, zero-drift reconciliation и удаление одноразовой БД. Это закрывает конкретный локальный дефект runner, **не** весь CP-15.

## 6. Порядок завершения текущего цикла

1. Выполнить CP-18 как свежий independent Audit 0–12 на baseline `593ddec0c9100b0df2eafe4f324c7bb600d75cba` / Alembic `b0c1d2e3f4a5`; для каждого ID фиксировать новое evidence, а не переносить старый PASS.
2. Особо перепроверить split ingress: direct `app.spik-inventory.ru` и dedicated `telegram-webhook.spik-inventory.ru` через Cloudflare Tunnel, runtime DB grants, release provenance, backup/recovery assumptions и Telegram delivery.
3. Исправить только реально воспроизведённые блокеры и повторить затронутые gates.
4. После CP-18 выполнить финальную Markdown-консолидацию: перенести актуальные требования, обновить ссылки/contracts, удалить отработавшие audit/history документы по принятой политике.
5. После очистки оставить `ROADMAP.md` единственным актуальным планом дальнейшей разработки.

Команды развёртывания, восстановления и критерии остановки не копируем в roadmap: их владельцы — [DEPLOYMENT.md](DEPLOYMENT.md), [OPERATIONS.md](OPERATIONS.md), [RECOVERY_RUNBOOK.md](RECOVERY_RUNBOOK.md) и [CP07_HTTP_SOCKET_MIGRATION.md](CP07_HTTP_SOCKET_MIGRATION.md).

## 10. Accepted clean baseline

Accepted production/runtime baseline текущего remediation cycle:

`593ddec0c9100b0df2eafe4f324c7bb600d75cba`

Подтверждено 25.09.2026:

- [x] immutable release/runtime provenance match;
- [x] Alembic `b0c1d2e3f4a5`;
- [x] runtime DB role cutover и zero-drift reconciliation;
- [x] direct host ingress + Unix socket;
- [x] dedicated Cloudflare Tunnel для Telegram webhook;
- [x] real Telegram acceptance и post-deploy off-VM backup.

Этот baseline является исходной точкой CP-18, но перед будущим production change всё равно требуется новая live-проверка.

## 11. Работы вне текущего цикла

Без отдельного решения не добавляем частичную приёмку закупок, каталог поставщиков, счета/OCR, ERP, аналитику цен, динамические роли или учёт отдельных serial/WWN экземпляров. Новые функции не должны блокировать завершение уже определённого remediation cycle.
