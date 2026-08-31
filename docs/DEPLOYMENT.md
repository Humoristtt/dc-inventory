# Развёртывание

## Принцип

Production VM не является development-машиной.

Изменения проходят следующий путь:

    Mac
      -> Git
      -> GitHub
      -> проверенный commit
      -> production VM

Production VM имеет read-only GitHub Deploy Key. Deploy выполняется только из конкретного SHA, успешно прошедшего CI.

## Production runtime

Production Compose находится в `compose.yaml`.

Схема:

    Telegram / Browser
          ↓
       Cloudflare
          ↓
    Cloudflare Tunnel
          ↓
    127.0.0.1:8080
          ↓
        Nginx
       ├── React
       └── /api
            ↓
          FastAPI
            ↓
        PostgreSQL

На host публикуется только:

    127.0.0.1:8080

Backend и PostgreSQL host-портов не имеют.

PostgreSQL и migration container находятся в отдельной внутренней Docker-сети. Nginx не имеет прямого сетевого доступа к PostgreSQL.

## Cloudflare Tunnel

`cloudflared` работает на production VM как systemd service и подключается к локальному origin:

    http://localhost:8080

Ожидаемый публичный hostname Mini App:

    https://app.spik-inventory.ru

Tunnel token является секретом и не хранится в Git или документации.

## Reverse proxy

Cloudflare передаёт исходную схему запроса в `X-Forwarded-Proto`, а IP посетителя — в `CF-Connecting-IP`.

Nginx нормализует эти значения и передаёт backend `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Real-IP` и `X-Forwarded-For`.

Uvicorn доверяет proxy headers, потому что production backend не публикуется на host и доступен только через внутреннюю application-сеть.

## Секреты

Production `.env` создаётся непосредственно на VM и не хранится в Git.

Минимально необходимы:

    POSTGRES_DB
    POSTGRES_USER
    POSTGRES_PASSWORD
    DATABASE_URL

`DATABASE_URL` внутри Docker network должен использовать hostname `postgres`.

Пример формы:

    postgresql+asyncpg://USER:PASSWORD@postgres:5432/DATABASE

## Миграции

Перед backend запускается одноразовый контейнер:

    alembic upgrade head

Backend запускается только после успешного завершения migration container.

Предметные миграции должны быть безопасны для последовательного deploy. Для потенциально разрушительных изменений обязателен backup и заранее определённый rollback/forward-fix план.

## Проверка после deploy

    curl http://127.0.0.1:8080/healthz
    curl http://127.0.0.1:8080/api/health/live
    curl http://127.0.0.1:8080/api/health/ready

Ожидается HTTP 200 для всех трёх запросов.

Также проверяются:

- `postgres`, `backend`, `web` — healthy;
- `migrate` — `Exited (0)`;
- на host отсутствуют listen-порты `8000` и `5432`;
- backend работает от UID 10001;
- web работает от пользователя `nginx`;
- SHA production worktree совпадает с утверждённым deploy SHA.

## Backup

До загрузки первых канонических складских данных должен быть реализован PostgreSQL backup/restore runbook и выполнен хотя бы один тест восстановления.
