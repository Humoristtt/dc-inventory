# Документация Spikatel Inventory

Эта директория содержит только **актуальную документацию текущей реализации**. Исторические журналы, старые аудиты, этапные планы, прошлые release SHA и устаревшие remediation-ledger здесь не используются как источник истины.

При расхождении приоритет такой:

1. фактически исполняемый код, миграции и runtime-конфигурация;
2. regression/contract tests;
3. текущая документация;
4. внешние организационные материалы.

Если документация расходится с кодом, исправляется документация или код — расхождение не объявляется «исторической особенностью».

## Карта документов

| Документ | Ответственность |
|---|---|
| [../README.md](../README.md) | краткое описание продукта, инварианты и текущий source baseline |
| [../AGENTS.md](../AGENTS.md) | правила инженерной работы в репозитории |
| [CURRENT_STATE_AUDIT.md](CURRENT_STATE_AUDIT.md) | чистый аудит текущего `main`: область, evidence, findings, ограничения |
| [ARCHITECTURE.md](ARCHITECTURE.md) | компоненты, сети, request paths, транзакции и trust boundaries |
| [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) | функциональный контракт и non-goals |
| [ACCESS_AND_RBAC.md](ACCESS_AND_RBAC.md) | Telegram auth, sessions, access lifecycle, roles/capabilities |
| [CATALOG.md](CATALOG.md) | Category/Manufacturer/Item/EAV, identity, search и facets |
| [WAREHOUSE.md](WAREHOUSE.md) | StorageLocation, Movement, stock/custody projections, locks и reconciliation |
| [PROCUREMENT.md](PROCUREMENT.md) | request/revision/event lifecycle, idempotency и technical acceptance |
| [NOTIFICATIONS.md](NOTIFICATIONS.md) | Telegram/email outbox, workers и delivery semantics |
| [FRONTEND.md](FRONTEND.md) | React architecture, routing, Telegram integration, design system и performance contracts |
| [SECURITY.md](SECURITY.md) | security model, secrets, DB grants, container/network boundaries, supply chain |
| [DEVELOPMENT.md](DEVELOPMENT.md) | dev setup, migrations, focused/full tests |
| [DEPLOYMENT.md](DEPLOYMENT.md) | release artifacts, controlled deployment и post-deploy verification |
| [OPERATIONS.md](OPERATIONS.md) | runtime health, workers, ingress, DB roles, backup monitoring и incident checks |
| [RECOVERY_RUNBOOK.md](RECOVERY_RUNBOOK.md) | безопасное изолированное восстановление и отдельная production cutover boundary |
| [../frontend/vendor/telegram-web-app.SOURCE.md](../frontend/vendor/telegram-web-app.SOURCE.md) | provenance vendored Telegram Web App SDK |

## Правила документации

- Не хранить отдельные «планы аудита», «истории исправлений» и дублирующие статусные ledgers.
- Не выдавать прошлый production SHA, старый Alembic head или старый backup object за текущий факт.
- Source baseline разрешено фиксировать только в датированном [CURRENT_STATE_AUDIT.md](CURRENT_STATE_AUDIT.md).
- `OPERATIONS.md` описывает, **как измерить live state**, а не подменяет измерение старой записью.
- `DEPLOYMENT.md` описывает процедуру изменения production; `DEVELOPMENT.md` не является deployment runbook.
- Предметный инвариант описывается в одном domain-документе, остальные документы ссылаются на него.
- Новая документация должна быть на русском, кроме имён API, файлов, переменных, сущностей и общеупотребимых технических терминов.

## Обязательная проверка

После изменения Markdown:

```bash
python3 ops/tests/test_docs_structure.py
python3 ops/tests/test_docs_freshness.py
python3 ops/tests/test_repository_data_policy.py
python3 ops/tests/test_notification_delivery_contract.py
python3 ops/tests/test_recovery_runbook_contract.py
git diff --check
```

Документационные тесты проверяют актуальный контракт. Они не должны требовать существования удалённых исторических документов.
