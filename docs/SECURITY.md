# Безопасность Spikatel Inventory

Документ описывает текущие технические границы безопасности репозитория. Он не является penetration-test report и не подтверждает live production без отдельной runtime-проверки.

## 1. Модель доверия

Доверяем:

- PostgreSQL constraints/triggers как database boundary;
- backend capability checks как application authorization boundary;
- host/web Nginx как ingress normalization boundary;
- Git SHA + immutable image ID как release identity;
- versioned S3 object ID + SHA-256 как backup identity.

Не доверяем:

- frontend visibility;
- входящим client IP/forwarded headers из публичного запроса;
- Telegram `initData` без проверки подписи/freshness;
- свободной строке роли/capability от клиента;
- данным route state как каноническому server state;
- старым документам или прошлым production SHA как доказательству live state.

## 2. Authentication и session security

Telegram authentication:

- проверяет signature HMAC;
- запрещает duplicate fields;
- ограничивает длину payload и число полей;
- проверяет `auth_date` по max age/future skew;
- Telegram user ID берётся из verified payload.

Session:

- случайный token генерируется через `secrets.token_urlsafe`;
- в БД хранится SHA-256 hash;
- cookie HttpOnly;
- session имеет TTL и revoked state;
- число активных сессий пользователя ограничено;
- BLOCKED/recovery operations отзывают sessions.

State-changing cookie requests требуют подходящего `Origin`.

## 3. Authorization

Backend capabilities определяются серверной role policy. Endpoint dependencies требуют:

1. существующую валидную session;
2. `APPROVED` access status;
3. конкретную capability.

Frontend capability checks предназначены для UX и не заменяют backend.

OWNER — singleton recovery identity. Обычный admin API не может менять OWNER/recovery user. Изменения access/role audit-coupled на PostgreSQL boundary.

## 4. Mutation safety gate

`REAL_INVENTORY_MUTATIONS_ENABLED=false` — default.

Gate применяется к операциям, которые меняют реальный каталог/склад и к Procurement operations, которые создают Catalog Item или Warehouse RECEIPT. Это operational safety switch, а не RBAC.

## 5. Database least privilege

Runtime identities разделены:

- DB owner — migrations/grants;
- application runtime — API domain work;
- Telegram worker — notification outbox + необходимый Telegram chat state;
- email worker — email outbox;
- maintenance worker — select/delete только технических retention tables.

Ключевые свойства:

- runtime не имеет schema CREATE;
- projections read-only для runtime и меняются через разрешённую DB function;
- immutable warehouse/procurement history не имеет UPDATE/DELETE grant;
- identity table UPDATE column-scoped;
- Telegram outbox update column-scoped;
- workers не получают доступ к чужим outbox/domain tables.

Права применяются через `psql -X --single-transaction -v ON_ERROR_STOP=1`. Legacy worker NOLOGIN/revoke фиксируется до отдельного post-commit завершения старых sessions.

## 6. Ingress

Host Nginx:

- unknown HTTP host возвращает 444;
- unknown HTTPS handshake отвергается;
- разрешён public application hostname;
- TLS 1.2/1.3;
- проксирование production user traffic — через Unix socket.

Web Nginx:

- не доверяет публичному `CF-Connecting-IP`;
- нормализует `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`;
- применяет API и sensitive endpoint rate limits;
- включает HSTS, X-Content-Type-Options, Referrer-Policy, CSP и Permissions-Policy.

Backend не публикуется на host interface.

## 7. Container hardening

Production-shaped services используют по возможности:

- non-root runtime user;
- read-only root filesystem;
- tmpfs для runtime write paths;
- `cap_drop: ALL`;
- `no-new-privileges:true`;
- `pids_limit`;
- CPU/memory limits;
- bounded local log rotation.

Backend, DB и maintenance не имеют external egress network. Egress получают только delivery workers.

## 8. Secrets

В Git запрещены:

- real `.env`;
- Telegram bot/webhook/gateway tokens;
- PostgreSQL passwords;
- Microsoft Graph credentials;
- private keys;
- real inventory workbook/dataset;
- DB dumps;
- **private/runtime-only production identifiers**.

**Public service identifiers** могут быть в репозитории, если они необходимы для публичного маршрута или документации.

`.env.example` содержит только placeholders. `ops/validate_env_file.py --production` запрещает неизвестные keys, оставшиеся `replace-with-` placeholders и не-URL-safe DB secrets, которые интерполируются в connection URL.

## 9. Supply chain

CI проверяет:

- GitHub Actions refs pinned на 40-char commit SHA;
- external base images pinned по digest;
- backend Python dependencies устанавливаются с `--require-hashes`;
- frontend lockfile проходит `npm audit --audit-level=high`;
- vendored Telegram Web App SDK проверяется по SHA-256 и размеру;
- Trivy filesystem scan HIGH/CRITICAL;
- финальные backend/web/postgres image scans HIGH/CRITICAL.

Прежний npm HIGH signal был локализован до транзитивного `undici 8.10.1` через `jsdom` и закрыт обновлением lockfile до `undici 8.10.2`. Текущий CI получает `found 0 vulnerabilities`.

Backend PCRE2 security package фиксируется версией и SHA-256 официального Debian Security pool artifact для amd64/arm64. Это исключает зависимость сборки от ротации moving apt index; после установки финальный image всё равно обязан пройти Trivy HIGH/CRITICAL gate.

## 10. Data integrity security

Critical invariants реализованы и на DB boundary:

- append-only warehouse/procurement/audit history;
- Catalog identity derivation;
- required/typed EAV;
- role/access audit coupling;
- custody eligibility;
- Procurement final movement binding;
- current revision ownership.

Readiness fail-closed проверяет наличие критических DB objects.

## 11. External delivery

Внешняя доставка Telegram/email имеет семантику **at-least-once**. Dedupe защищает запись intent, но не превращает внешний provider side effect в exactly-once.


Telegram Gateway:

- whitelist Bot API methods;
- shared gateway secret;
- constant-time style digest comparison;
- body limit 64 KiB;
- no arbitrary upstream method/path proxying.

Backend gateway client:

- HTTPS required in production;
- redirects disabled;
- response bounded 1 MiB;
- safe errors не включают secret/token.

Email worker запускается только при `EMAIL_DELIVERY_ENABLED=true` и полном Microsoft Graph config.

## 12. Repository visibility

Репозиторий рассматривается как публичный. Поэтому документация и tests не должны содержать секреты, private runtime identifiers или реальные наборы inventory.

Автоматический `test_repository_data_policy.py` проверяет tracked env/key/token patterns, но не заменяет review.
