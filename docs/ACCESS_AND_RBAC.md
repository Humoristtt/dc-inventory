# Authentication, Access и RBAC

Backend является единственной границей авторизации. Frontend использует тот же набор capabilities только для UX.

## 1. Сущности

**User** хранит UUID, `role`, `access_status`, timestamps и approval metadata.

**TelegramIdentity** связывает Telegram user ID с User и хранит отображаемые Telegram attributes.

**AuthSession** хранит hash server-side session token, TTL и optional revoke timestamp.

**AccessRequest** — отдельная заявка пользователя на доступ.

**UserAccessEvent / UserRoleEvent** — immutable audit history изменения access/role.

## 2. Первый вход

```text
Telegram WebApp initData
        │
        ▼
POST /api/auth/telegram
        │
        ├── parse bounded payload
        ├── reject duplicate fields
        ├── verify Telegram HMAC
        ├── verify auth_date freshness
        ├── lock/reconcile identity
        ├── reconcile recovery OWNER if applicable
        └── create AuthSession
                 │
                 ▼
            HttpOnly cookie
```

Concurrent first login одного Telegram ID сериализуется advisory lock.

## 3. Повторный вход

`GET /api/auth/me` получает session token из cookie, хеширует его и ищет активную непросроченную session вместе с User/TelegramIdentity.

Если cookie session валидна, Telegram SDK не нужен для каждого запроса.

## 4. Origin protection

Для cookie-authenticated `POST/PUT/PATCH/DELETE` backend проверяет `Origin`:

- source должен совпадать с configured `TELEGRAM_WEB_APP_URL`;
- GET/HEAD/OPTIONS не требуют этой проверки;
- отсутствие/несовпадение Origin отклоняется.

## 5. Access lifecycle

```text
новый User
  │
  ▼
PENDING ── approve ──► APPROVED
  │                      │
  ├── reject ─────────► REJECTED
  │                      │
  │                    block
  │                      ▼
  └──────────────────► BLOCKED
```

REJECTED user может подать новую заявку. BLOCKED не получает обычный доступ.

## 6. Capability matrix

Фактическая server policy:

| Capability | ENGINEER | SENIOR_ENGINEER | MANAGER | ADMIN | OWNER |
|---|:---:|:---:|:---:|:---:|:---:|
| `catalog.read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `catalog.manage` |  | ✓ |  | ✓ | ✓ |
| `catalog.archive` |  | ✓ |  | ✓ | ✓ |
| `catalog.delete_unused` |  | ✓ |  | ✓ | ✓ |
| `inventory.read` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `inventory.operate` | ✓ | ✓ |  | ✓ | ✓ |
| `inventory.admin` |  |  |  | ✓ | ✓ |
| `movement.read_own` | ✓ | ✓ |  |  |  |
| `movement.read_all` |  | ✓ |  | ✓ | ✓ |
| `procurement.read` |  | ✓ | ✓ | ✓ | ✓ |
| `procurement.create` |  |  |  | ✓ | ✓ |
| `procurement.manage` |  |  | ✓ |  |  |
| `procurement.accept` |  | ✓ |  | ✓ | ✓ |
| `access.manage_users` |  |  |  | ✓ | ✓ |
| `access.assign_standard_roles` |  |  |  | ✓ | ✓ |
| `access.assign_admin` |  |  |  |  | ✓ |

Важно: `MANAGER` — отдельная предметная ветка, а не «уровень выше SENIOR_ENGINEER». ADMIN не получает `procurement.manage` автоматически.

## 7. OWNER

OWNER — singleton recovery identity.

Защиты:

- обычный target-aware access policy не позволяет ADMIN управлять OWNER;
- OWNER не меняется обычной role mutation;
- recovery identity не сбрасывается через обычный account reset;
- reconciliation использует global identity management advisory lock;
- только OWNER имеет `access.assign_admin`.

Recovery OWNER создаётся/восстанавливается из configured Telegram ID при authentication flow.

## 8. Изменение доступа

Admin operation:

1. загружает actor/target;
2. берёт общий identity management lock;
3. блокирует нужные User rows;
4. проверяет target policy;
5. проверяет outstanding custody;
6. проверяет active Procurement responsibility;
7. меняет status;
8. создаёт `UserAccessEvent`;
9. при BLOCKED отзывает sessions;
10. commit выполняет API boundary.

PostgreSQL deferred trigger не позволяет изменить `users.access_status` без соответствующего audit event в той же транзакции.

## 9. Изменение роли

Алгоритм аналогичен access mutation.

Нельзя:

- менять собственную role;
- менять OWNER/recovery identity;
- non-OWNER actor менять ADMIN target;
- назначать role вне actor capabilities;
- переводить user в role, несовместимую с текущим custody/active Procurement responsibility.

DB deferred trigger требует `UserRoleEvent`.

## 10. Account reset

Reset нужен для пере-привязки Telegram identity без удаления audit history.

Он:

- запрещён для self/OWNER/recovery target;
- target ADMIN требует OWNER;
- запрещён при outstanding custody/active procurement;
- отзывает sessions;
- удаляет TelegramIdentity;
- удаляет pending access requests;
- сохраняет User и immutable audit history;
- переводит user в безопасное состояние для повторной регистрации.

## 11. Frontend

`TelegramAccessGate`:

1. пробует cookie auth;
2. при 401 загружает vendored Telegram SDK;
3. выполняет Telegram auth;
4. для PENDING опрашивает access state;
5. рендерит приложение только для APPROVED.

Page-level guards скрывают/редиректят UX, но не считаются security control.

## 12. Проверки

Критичные regression areas:

- Telegram initData;
- auth session limit/revocation;
- recovery OWNER;
- access/role PostgreSQL invariants;
- cross-channel Telegram/Web access parity;
- account reset;
- runtime DB role column permissions;
- frontend RBAC.
