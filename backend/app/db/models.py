"""Центральный реестр ORM-моделей для Alembic metadata discovery."""

from app.modules.auth.models import AuthSession
from app.modules.catalog.models import (
    Category,
    CategoryAttribute,
    Item,
    ItemAttributeValue,
    Manufacturer,
)
from app.modules.identity.models import (
    AccessRequest,
    TelegramIdentity,
    User,
    UserAccessEvent,
)
from app.modules.inventory.models import (
    Location,
    Movement,
    MovementLine,
    StockBalance,
    UserItemCustodyBalance,
)
from app.modules.notifications.models import NotificationOutbox
from app.modules.telegram_bot.models import (
    AccessDecisionCallback,
    TelegramChatState,
    TelegramUpdate,
)

__all__ = [
    "AccessDecisionCallback",
    "AccessRequest",
    "AuthSession",
    "Category",
    "CategoryAttribute",
    "Item",
    "ItemAttributeValue",
    "Location",
    "Manufacturer",
    "Movement",
    "MovementLine",
    "NotificationOutbox",
    "StockBalance",
    "UserItemCustodyBalance",
    "TelegramChatState",
    "TelegramIdentity",
    "TelegramUpdate",
    "User",
    "UserAccessEvent",
]
