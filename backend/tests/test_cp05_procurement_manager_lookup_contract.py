import uuid
from inspect import signature

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.enums import UserRole
from app.modules.identity.models import TelegramIdentity
from app.modules.procurement.api import get_managers
from app.modules.procurement.service import list_managers
from tests.warehouse_helpers import actor


def test_manager_lookup_accepts_server_side_search_contract() -> None:
    assert "q" in signature(get_managers).parameters
    assert "query" in signature(list_managers).parameters


@pytest.mark.asyncio
async def test_manager_lookup_searches_identity_and_paginates(
    warehouse_db: AsyncSession,
) -> None:
    marker = f"cp05-{uuid.uuid4().hex[:12]}"

    first, _ = await actor(
        warehouse_db,
        UserRole.MANAGER,
    )
    second, _ = await actor(
        warehouse_db,
        UserRole.MANAGER,
    )
    await actor(
        warehouse_db,
        UserRole.MANAGER,
    )

    first_identity = await warehouse_db.scalar(
        select(TelegramIdentity).where(TelegramIdentity.user_id == first.id)
    )
    second_identity = await warehouse_db.scalar(
        select(TelegramIdentity).where(TelegramIdentity.user_id == second.id)
    )

    assert first_identity is not None
    assert second_identity is not None

    first_identity.first_name = marker
    first_identity.last_name = "Alpha"
    first_identity.username = f"{marker}-alpha"

    second_identity.first_name = marker
    second_identity.last_name = "Beta"
    second_identity.username = f"{marker}-beta"

    await warehouse_db.flush()

    page_one, total_one, names_one = await list_managers(
        warehouse_db,
        query=marker,
        limit=1,
        offset=0,
    )

    page_two, total_two, names_two = await list_managers(
        warehouse_db,
        query=marker,
        limit=1,
        offset=1,
    )

    assert total_one == 2
    assert total_two == 2
    assert len(page_one) == 1
    assert len(page_two) == 1
    assert page_one[0].id != page_two[0].id

    first_name = names_one[page_one[0].id]
    second_name = names_two[page_two[0].id]

    assert marker in first_name
    assert marker in second_name
