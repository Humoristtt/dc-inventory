import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_inventory_api_postgres import api_context
from tests.warehouse_helpers import cable_payload

pytestmark = pytest.mark.asyncio


async def test_catalog_api_read_admin_and_gate_boundaries(warehouse_db: AsyncSession) -> None:
    app, users = await api_context(warehouse_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/api/catalog/categories", "/api/catalog/items", "/api/catalog/items/facets"):
            assert (await client.get(path)).status_code == 401
            for name in ("pending", "blocked", "rejected"):
                assert (await client.get(path, headers=users[name][1])).status_code == 403
            for name in ("user", "senior", "manager", "admin", "owner"):
                assert (await client.get(path, headers=users[name][1])).status_code == 200
        payload = cable_payload().model_dump(mode="json")
        path = "/api/admin/catalog/items"
        assert (await client.post(path, headers=users["user"][1], json=payload)).status_code == 403
        assert (
            await client.post(
                path,
                headers=users["manager"][1],
                json=payload,
            )
        ).status_code == 403

        senior_response = await client.post(
            path,
            headers=users["senior"][1],
            json=cable_payload().model_dump(mode="json"),
        )
        assert senior_response.status_code == 201, senior_response.text
        senior_item_id = senior_response.json()["id"]
        assert (
            await client.post(
                f"{path}/{senior_item_id}/archive",
                headers=users["senior"][1],
            )
        ).status_code == 200
        assert (
            await client.post(
                path, headers={**users["admin"][1], "Origin": "https://evil.example"}, json=payload
            )
        ).status_code == 403
        response = await client.post(path, headers=users["admin"][1], json=payload)
        assert response.status_code == 201, response.text
        item_id = response.json()["id"]
        assert response.json()["category"]["key"] == "optical_patch_cord"
        duplicate = await client.post(path, headers=users["admin"][1], json=payload)
        assert duplicate.status_code == 409
        patch = await client.patch(
            f"{path}/{item_id}", headers=users["admin"][1], json={"name": "Updated"}
        )
        assert patch.status_code == 200 and patch.json()["name"] == "Updated"
        for action, expected in [("archive", "ARCHIVED"), ("unarchive", "ACTIVE")]:
            response = await client.post(f"{path}/{item_id}/{action}", headers=users["admin"][1])
            assert response.status_code == 200 and response.json()["status"] == expected
        owner_response = await client.post(
            path,
            headers=users["owner"][1],
            json=cable_payload().model_dump(mode="json"),
        )
        assert owner_response.status_code == 201, owner_response.text
        app.state.settings.real_inventory_mutations_enabled = False
        assert (await client.post(path, headers=users["admin"][1], json=payload)).status_code == 423
