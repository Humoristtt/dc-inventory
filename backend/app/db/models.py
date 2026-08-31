"""Центральный реестр ORM-моделей для Alembic metadata discovery."""

from app.modules.auth.models import AuthSession
from app.modules.identity.models import AccessRequest, TelegramIdentity, User

__all__ = ["AccessRequest", "AuthSession", "TelegramIdentity", "User"]
