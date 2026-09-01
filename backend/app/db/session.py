from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    engine = cast(AsyncEngine, request.app.state.db_engine)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
