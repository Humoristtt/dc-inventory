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
