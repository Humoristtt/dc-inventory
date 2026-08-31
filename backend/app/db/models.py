"""Центральный реестр ORM-моделей для Alembic metadata discovery."""

from app.modules.identity.models import AccessRequest, TelegramIdentity, User

__all__ = ["AccessRequest", "TelegramIdentity", "User"]
