# DC Inventory

Telegram Mini App for datacenter equipment inventory and movement tracking.

## Core principles

- PostgreSQL-backed inventory ledger is the source of truth.
- Inventory changes are represented as immutable movements.
- Supports quantity-based and serial-number-based inventory.
- Multiple warehouse / datacenter locations.
- Telegram authentication with ADMIN and USER roles.
- Administrative Telegram notifications for equipment withdrawals.
- Production is deployed from reviewed Git commits.
- Production VM has read-only access to this repository.

## Planned stack

- React + TypeScript + Vite
- FastAPI
- PostgreSQL
- SQLAlchemy + Alembic
- aiogram
- Docker Compose
- Nginx
- Cloudflare Tunnel
