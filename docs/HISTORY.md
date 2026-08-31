# История проекта

Здесь фиксируются ключевые этапы развития проекта, инфраструктурные изменения и архитектурные решения.

## 2026-08-31 — Инициализация проекта

- Создан private-репозиторий `Humoristtt/dc-inventory`.
- Первый commit: `d889f3bcc4a31d9bd8660eb8827afad3e73fffe6`.
- Подготовлена production VM `dc-inventory` на Ubuntu Server 24.04.4 LTS.
- Выделено 4 vCPU, 8 GB RAM, 100 GB disk и 2 GB swap.
- Root filesystem расширен через LVM примерно до 98 GB.
- Настроен SSH только по ключу; password authentication и root login отключены.
- Настроен локальный SSH alias `ssh inventory`.
- Установлены Docker Engine, Docker Compose и containerd из официального Docker repository.
- Для Docker включены `live-restore` и ограничение размера container logs.
- Production VM получила отдельный read-only GitHub Deploy Key `dc-inventory-prod`.
- Проверен доступ к GitHub, Docker Hub и Cloudflare.
- Установлено, что прямое TCP-соединение VM к `api.telegram.org:443` завершается timeout до TLS handshake.
- Принято решение не направлять весь трафик VM через VPN/WARP; Telegram Bot API будет обслуживаться через отдельный безопасный gateway.
- Получены исходные Excel-файлы текущей складской номенклатуры.
- Получены фирменный guidebook Spikatel 2026 и оригинальные web-логотипы.
- Документация проекта ведётся на русском языке и должна обновляться вместе с реализацией.

## 2026-08-31 — Backend runtime foundation

- Создан backend foundation на Python 3.12 и FastAPI.
- Зафиксирован архитектурный стиль модульного монолита.
- Выделены инфраструктурные слои `api`, `core`, `db` и каталог будущих предметных модулей `modules`.
- Настроен SQLAlchemy 2 в async-режиме через `asyncpg`.
- Добавлена обязательная конфигурация `DATABASE_URL`.
- Добавлен ограниченный timeout подключения к PostgreSQL.
- Настроен Alembic в async-режиме.
- Строка подключения к PostgreSQL не хранится в `alembic.ini`.
- Создан baseline Alembic `48c2f07f01a0`.
- Добавлен PostgreSQL 18 для локальной разработки через `compose.dev.yaml`.
- Development PostgreSQL публикуется только на `127.0.0.1:55432`.
- Локальный `.env` исключён из Git; добавлен `.env.example`.
- Реализован `/api/health/live`.
- Реализован `/api/health/ready` с реальной проверкой PostgreSQL.
- DB health logic вынесена из HTTP-слоя в `app/db/health.py`.
- Настроены Ruff, mypy strict и Pytest.
- Unit tests проверяют успешный readiness и ответ HTTP 503 при недоступной БД.
- Выполнен acceptance с реальным PostgreSQL: `UP -> 200/200`, `DOWN -> 200/503`, `BACK -> 200/200`.
- Подтверждено восстановление readiness без рестарта backend.
- Для будущих автоматизированных runtime-проверок вместо фиксированных задержек будет использоваться bounded readiness polling.

## 2026-08-31 — Production-shaped runtime foundation

- Добавлен production Compose `compose.yaml`.
- В production на host публикуется только Nginx на `127.0.0.1:8080`.
- Backend и PostgreSQL не публикуют host-порты.
- Добавлен `requirements-dev.lock` с hash-locked development/CI-зависимостями.
- Добавлен GitHub Actions CI для backend, frontend, миграций и сборки Docker images.
- Удалены остаточные файлы стандартного Vite scaffold.
- Добавлена deployment-документация.

## 2026-08-31 — Архитектурный pre-feature hardening

- Проведён полный аудит runtime foundation перед Telegram authentication и первой предметной миграцией.
- Добавлен naming convention SQLAlchemy до появления предметных constraints.
- Зафиксированы DB pool, statement timeout и lock timeout boundaries.
- PostgreSQL runtime sessions закреплены в UTC.
- Production Swagger/OpenAPI отключены.
- Исправлена proxy-chain семантика Cloudflare -> Nginx -> Uvicorn для scheme и client IP.
- PostgreSQL изолирован от web отдельной internal Docker network.
- CI расширен production-shaped runtime smoke test через Nginx, FastAPI, Alembic и PostgreSQL.
- Обновлена canonical документация frontend/runtime/deployment.
