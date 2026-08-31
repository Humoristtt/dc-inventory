import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://dc_inventory:test-only@127.0.0.1:5432/dc_inventory",
)
