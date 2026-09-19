# План разработки Spikatel Inventory

Актуализировано 19.09.2026. `[x]` — реализовано/исторически принято в указанном контуре, `[~]` — локально проверено, но приёмка не завершена, `[ ]` — не выполнено. Реальное production-состояние нельзя выводить из локального Git HEAD. История закрытых работ — `docs/HISTORY.md`; журнал CP-00–18 — `docs/AUDIT_0_12_REMEDIATION.md`.

## 1. Базовая платформа

- [x] Telegram Mini App, FastAPI, PostgreSQL, Docker Compose, Cloudflare HTTPS/Tunnel.
- [x] Telegram initData server-side validation, HttpOnly session, access requests и approve/reject.
- [x] Five-role RBAC с backend-derived capabilities.
- [x] Transactional notification outbox и раздельные PostgreSQL identities.
- [x] Fail-closed boundary `REAL_INVENTORY_MUTATIONS_ENABLED=false`.

## 2. Warehouse Domain V2

- [x] Quantity-only inventory без active physical-unit/serial lifecycle.
- [x] `StockBalance = Item × Location × positive quantity`.
- [x] `UserItemCustodyBalance = User × Item × positive quantity`.
- [x] Actor отделён от custody; ENGINEER/SENIOR_ENGINEER ISSUE/RETURN меняют custody.
- [x] Zero rows не хранятся, negative stock/custody запрещены.
- [x] StorageLocation WAREHOUSE/DATACENTER; архивирование локации с остатком запрещено.
- [x] Immutable journal: RECEIPT, ISSUE, RETURN, TRANSFER, WRITE_OFF, CORRECTION, REVERSAL.
- [x] Idempotency, ordered PostgreSQL locks, read-only projection reconciliation.
- [x] Финальный procurement RECEIPT защищён от generic CORRECTION/REVERSAL в source.

## 3. Роли и операции

- [x] ENGINEER — каталог/остатки/свои движения; ISSUE, RETURN, RECEIPT существующей позиции, TRANSFER.
- [x] SENIOR_ENGINEER — операции ENGINEER, общий журнал, управление каталогом, technical procurement acceptance.
- [x] MANAGER — каталог/остатки/закупки; без складских mutations и общего журнала.
- [x] ADMIN/OWNER — складские и catalog administration, роли/доступ, technical acceptance.
- [x] OWNER singleton/recovery; ADMIN не назначает ADMIN/OWNER; защита реализована backend.

## 4. Каталог и интерфейс

- [x] Fixed family → leaf hierarchy: Ethernet/FC трансиверы и адаптеры, оптика, SSD/HDD, RAM, PCIe, питание.
- [x] Leaf-schema attributes, нормализация reach, «Дальние» как derived scope, optional color.
- [x] Dynamic scoped facets, search, карточки, stock by location, create/edit/archive.
- [x] Warehouse actions, capability-aware journal, фильтры и периоды.
- [x] Responsive shared UI design system и performance acceptance прошлого цикла.
- [x] Archived Item запрещает новый RECEIPT/ISSUE, но допускает завершение существующего остатка.

## 5. Initial inventory bootstrap

- [x] Внешний workbook parser, validation, identity normalization и aggregation.
- [x] Guarded one-shot production bootstrap: empty domain, mutation gate закрыт, atomic location + opening RECEIPT.
- [x] Initial bootstrap завершён и повторно не запускается.
- [x] Counts/quantity check, ZERO_DRIFT reconciliation, post-import off-VM backup и Telegram visual acceptance.

## 6. Procurement и доставка

- [x] Production RBAC maintenance cutover.
- [x] Procurement domain на production migration `c3d4e5f6a7b8`: immutable revisions/events, manager collaboration, discrepancy без stock mutation, ровно один final RECEIPT.
- [x] Source migration head `a9c0d1e2f3a4`: дополнительные предметные/DB инварианты реализованы, но не развёрнуты автоматически.
- [x] ISSUE notification и procurement notifications используют транзакционный outbox с dedupe key.
- [x] Optional Microsoft Graph OAuth, To/CC, email outbox/retry/DEAD и отдельная DB identity реализованы в source.
- [ ] Production email credentials, `EMAIL_DELIVERY_ENABLED=true`, Compose profile `email` и live acceptance.
- [ ] Real Telegram Procurement acceptance текущего release.

Внешняя доставка Telegram/email — **at-least-once**, не exactly-once. При потере ответа шлюза возможно повторное сообщение/письмо даже при дедупликации outbox intent.

## 10. Accepted clean baseline

Accepted production/runtime golden baseline перед новым feature cycle:

`1242f56c131d0f8c470e05cbaf209c48a37e85a4`

Историческая приёмка предыдущего цикла:

- [x] required CI;
- [x] Warehouse V2/UX/design-system production acceptance;
- [x] real Telegram desktop acceptance и fresh verified production backup;
- [x] local/source/runtime golden-state verification.

Более поздняя зафиксированная production Procurement проверка: checkout/runtime `6d9bafef494f910b9bd1ebea7c5b7cf45f853742`, Alembic `c3d4e5f6a7b8`. Это историческая проверка, а не мониторинг текущего сервера. `REAL_INVENTORY_MUTATIONS_ENABLED=false` остаётся задокументированным production gate.

## 11. Текущий CP-00–CP-18 remediation cycle

Проверяемый объём, коммиты и ограничения: `docs/AUDIT_0_12_REMEDIATION.md`.

- [x] CP-00–CP-06: локальные результаты зафиксированы в журнале.
- [~] CP-07: trusted Unix-socket ingress проверен локально; Tunnel/web migration в production не выполнена.
- [~] CP-08: устранена гонка Telegram welcome/outbox; live delivery и Graph acceptance не проведены.
- [~] CP-09: права БД атомарны, legacy sessions завершаются после commit; production cutover не проведён.
- [~] CP-10: Git HEAD/provenance и release publication локально проверены; production images не сверялись.
- [~] CP-11: проверка backup manifest, cleanup и session revocation, одноразовый PostgreSQL restore; real S3/production rehearsal не выполнен.
- [~] CP-12: общий helper provenance в restore; локальные тесты прошли, независимый аудит впереди.
- [ ] CP-13: полная ревизия текущих Markdown и docs freshness gate.
- [ ] CP-14: isolated full-stack acceptance.
- [ ] CP-15: three-pass pre-deployment audit.
- [ ] CP-16: controlled production deployment.
- [ ] CP-17: real Telegram Mini App acceptance после deployment.
- [ ] CP-18: fresh independent Audit 0–12.

## 12. Операционная последовательность

Approved target SHA/CI → verified off-VM backup → согласованный maintenance/rollback plan → миграции и `db-permissions` → health, provenance, reconciliation, live smoke. CP-07 требует совместного переключения Tunnel и нового web image. Source-only sync без пересборки допустим только при неизменных Docker build contexts и runtime source; изменённые host-side `ops/` scripts требуют собственных syntax/contract checks. Production-зависимые CP-07–11 остаются OPEN до фактической проверки.

## 13. Дальнейший backlog

Без отдельного решения не входят в текущий цикл: partial procurement acceptance, supplier directory, invoices/OCR, ERP/accounting, dynamic custom roles, attachment storage, price analytics. Исторические решения и закрытые этапы не дублируются вместо `docs/HISTORY.md`.
