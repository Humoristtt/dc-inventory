import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.service import (
    AccessAlreadyApprovedError,
    AccessBlockedError,
    AccessRejectedError,
    create_or_get_access_request,
)
from app.modules.identity.enums import AccessRequestStatus, UserAccessStatus
from app.modules.identity.models import AccessRequest, User


@pytest.mark.asyncio
async def test_create_access_request_for_pending_user() -> None:
    user = User(id=uuid.uuid4(), access_status=UserAccessStatus.PENDING)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = user

    scalar_result = MagicMock()
    scalar_result.first.return_value = None
    db.scalars.return_value = scalar_result

    result = await create_or_get_access_request(db, user.id)

    assert result.created is True
    assert result.request.user_id == user.id
    assert result.request.status == AccessRequestStatus.PENDING
    db.add.assert_called_once_with(result.request)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_existing_pending_request_is_idempotent() -> None:
    user = User(id=uuid.uuid4(), access_status=UserAccessStatus.PENDING)
    existing = AccessRequest(
        id=uuid.uuid4(),
        user_id=user.id,
        status=AccessRequestStatus.PENDING,
    )
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = user

    scalar_result = MagicMock()
    scalar_result.first.return_value = existing
    db.scalars.return_value = scalar_result

    result = await create_or_get_access_request(db, user.id)

    assert result.created is False
    assert result.request is existing
    db.add.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("access_status", "error_type"),
    [
        (UserAccessStatus.APPROVED, AccessAlreadyApprovedError),
        (UserAccessStatus.REJECTED, AccessRejectedError),
        (UserAccessStatus.BLOCKED, AccessBlockedError),
    ],
)
async def test_access_request_rejects_non_pending_states(
    access_status: UserAccessStatus,
    error_type: type[Exception],
) -> None:
    user = User(id=uuid.uuid4(), access_status=access_status)
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = user

    with pytest.raises(error_type):
        await create_or_get_access_request(db, user.id)

    db.add.assert_not_called()
