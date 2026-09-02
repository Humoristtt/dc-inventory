from fastapi import APIRouter

from app.api.health import router as health_router
from app.modules.access.api import router as access_router
from app.modules.auth.api import router as auth_router
from app.modules.catalog.api import admin_router as admin_catalog_router
from app.modules.catalog.api import read_router as catalog_router
from app.modules.inventory.api import admin_router as admin_inventory_router
from app.modules.inventory.api import read_router as inventory_router
from app.modules.telegram_bot.api import router as telegram_router

api_router = APIRouter()
api_router.include_router(access_router)
api_router.include_router(admin_catalog_router)
api_router.include_router(catalog_router)
api_router.include_router(admin_inventory_router)
api_router.include_router(inventory_router)
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(telegram_router)
