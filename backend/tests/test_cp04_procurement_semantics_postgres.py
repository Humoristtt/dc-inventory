from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Item
from app.modules.identity.enums import UserRole
from app.modules.identity.policy import Capability, has_capability
from app.modules.procurement import service as procurement_service
from app.modules.procurement.schemas import CorrectionRequest
from app.modules.procurement.service import (
    ProcurementError,
    manager_accept,
)
from tests.test_procurement_postgres import (
    expected,
    seed_procurement,
)
from tests.warehouse_helpers import actor

pytestmark = pytest.mark.asyncio


async def test_cp04_revision_line_persists_expected_identity_signature(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    (
        _initiator,
        _manager,
        _senior,
        item_id,
        _location,
        record,
    ) = await seed_procurement(db)

    item = await db.get(Item, item_id)
    assert item is not None

    line = record.current_revision.lines[0]

    assert (
        getattr(
            line,
            "expected_identity_signature",
            None,
        )
        == item.identity_signature
    )


async def test_cp04_actor_capability_is_rechecked_after_request_serialization(
    warehouse_db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = warehouse_db

    (
        _initiator,
        manager,
        _senior,
        _item_id,
        _location,
        record,
    ) = await seed_procurement(db)

    serialized = False
    capability_checks_after_serialization = 0

    original_lock = procurement_service._lock_and_validate_expected
    original_has_capability = has_capability

    async def wrapped_lock(*args: Any, **kwargs: Any) -> Any:
        nonlocal serialized

        result = await original_lock(
            *args,
            **kwargs,
        )

        serialized = True
        return result

    def capability_after_serialization(
        role: UserRole,
        capability: Capability,
    ) -> bool:
        nonlocal capability_checks_after_serialization

        if serialized and capability == Capability.PROCUREMENT_MANAGE:
            capability_checks_after_serialization += 1
            return False

        return original_has_capability(
            role,
            capability,
        )

    monkeypatch.setattr(
        procurement_service,
        "_lock_and_validate_expected",
        wrapped_lock,
    )
    monkeypatch.setattr(
        procurement_service,
        "has_capability",
        capability_after_serialization,
    )

    with pytest.raises(ProcurementError):
        await manager_accept(
            db,
            record.request.id,
            expected(
                record,
                "cp04-post-lock-capability",
            ),
            actor_user_id=manager.id,
        )

    assert serialized is True
    assert capability_checks_after_serialization > 0

    await db.refresh(record.request)

    assert record.request.status.value == "AGREEMENT_PENDING_MANAGER"


async def test_cp04_revision_required_initiator_cannot_be_blocked(
    warehouse_db: AsyncSession,
) -> None:
    from app.modules.identity.admin_service import (
        AdminUserError,
        update_user_access,
    )
    from app.modules.identity.enums import (
        UserAccessStatus,
        UserRole,
    )
    from tests.test_cp01_cross_domain_regressions import create_existing_request, settings

    db = warehouse_db

    owner, _ = await actor(
        db,
        UserRole.OWNER,
        UserAccessStatus.APPROVED,
    )

    initiator, manager, _item_id, record = await create_existing_request(
        db,
        initiator_role=UserRole.ADMIN,
    )

    record = await procurement_service.return_for_correction(
        db,
        record.request.id,
        CorrectionRequest(
            expected_state_version=(record.request.state_version),
            expected_revision_id=(record.request.current_revision_id),
            client_request_id=(f"cp04-access-lifecycle-{record.request.id}"),
            comment="CP04 lifecycle guard",
        ),
        actor_user_id=manager.id,
        settings=settings(),
    )

    assert record.request.status.value == "AGREEMENT_REVISION_REQUIRED"

    with pytest.raises(AdminUserError):
        await update_user_access(
            db,
            actor_user_id=owner.id,
            target_user_id=initiator.id,
            access_status=UserAccessStatus.BLOCKED,
            recovery_telegram_user_id=None,
        )

    await db.refresh(initiator)

    assert initiator.access_status == UserAccessStatus.APPROVED
