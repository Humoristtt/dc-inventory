import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_inventory_api_postgres import api_context
from tests.warehouse_helpers import cable_payload

pytestmark = pytest.mark.asyncio


async def test_delete_unused_item_api_capabilities_and_gate(
    warehouse_db: AsyncSession,
) -> None:
    app, users = await api_context(warehouse_db)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        create_response = await client.post(
            "/api/admin/catalog/items",
            headers=users["senior"][1],
            json=cable_payload().model_dump(mode="json"),
        )
        assert create_response.status_code == 201
        item_id = create_response.json()["id"]
        path = f"/api/admin/catalog/items/{item_id}"

        assert (
            await client.delete(
                path,
                headers=users["user"][1],
            )
        ).status_code == 403

        assert (
            await client.delete(
                path,
                headers=users["manager"][1],
            )
        ).status_code == 403

        delete_response = await client.delete(
            path,
            headers=users["senior"][1],
        )
        assert delete_response.status_code == 204
        assert delete_response.content == b""

        read_response = await client.get(
            f"/api/catalog/items/{item_id}",
            headers=users["senior"][1],
        )
        assert read_response.status_code == 404

        create_response = await client.post(
            "/api/admin/catalog/items",
            headers=users["admin"][1],
            json=cable_payload().model_dump(mode="json"),
        )
        assert create_response.status_code == 201
        gated_item_id = create_response.json()["id"]

        app.state.settings.real_inventory_mutations_enabled = False

        gated_delete = await client.delete(
            f"/api/admin/catalog/items/{gated_item_id}",
            headers=users["admin"][1],
        )
        assert gated_delete.status_code == 423
