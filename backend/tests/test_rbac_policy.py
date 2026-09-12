import uuid

import pytest

from app.core.config import Settings
from app.modules.auth.api import _state_response
from app.modules.identity.enums import UserAccessStatus, UserRole
from app.modules.identity.models import TelegramIdentity, User
from app.modules.identity.policy import (
    ROLE_CAPABILITIES,
    Capability,
    serialized_capabilities,
)

EXPECTED = {
    UserRole.ENGINEER: {
        Capability.CATALOG_READ,
        Capability.INVENTORY_READ,
        Capability.INVENTORY_OPERATE,
        Capability.MOVEMENT_READ_OWN,
    },
    UserRole.SENIOR_ENGINEER: {
        Capability.CATALOG_READ,
        Capability.CATALOG_MANAGE,
        Capability.CATALOG_ARCHIVE,
        Capability.CATALOG_DELETE_UNUSED,
        Capability.INVENTORY_READ,
        Capability.INVENTORY_OPERATE,
        Capability.MOVEMENT_READ_OWN,
        Capability.MOVEMENT_READ_ALL,
        Capability.PROCUREMENT_READ,
        Capability.PROCUREMENT_ACCEPT,
    },
    UserRole.MANAGER: {
        Capability.CATALOG_READ,
        Capability.INVENTORY_READ,
        Capability.PROCUREMENT_READ,
        Capability.PROCUREMENT_MANAGE,
    },
    UserRole.ADMIN: {
        Capability.CATALOG_READ,
        Capability.CATALOG_MANAGE,
        Capability.CATALOG_ARCHIVE,
        Capability.CATALOG_DELETE_UNUSED,
        Capability.INVENTORY_READ,
        Capability.INVENTORY_OPERATE,
        Capability.INVENTORY_ADMIN,
        Capability.MOVEMENT_READ_ALL,
        Capability.PROCUREMENT_READ,
        Capability.PROCUREMENT_CREATE,
        Capability.PROCUREMENT_ACCEPT,
        Capability.ACCESS_MANAGE_USERS,
        Capability.ACCESS_ASSIGN_STANDARD_ROLES,
    },
    UserRole.OWNER: {
        Capability.CATALOG_READ,
        Capability.CATALOG_MANAGE,
        Capability.CATALOG_ARCHIVE,
        Capability.CATALOG_DELETE_UNUSED,
        Capability.INVENTORY_READ,
        Capability.INVENTORY_OPERATE,
        Capability.INVENTORY_ADMIN,
        Capability.MOVEMENT_READ_ALL,
        Capability.PROCUREMENT_READ,
        Capability.PROCUREMENT_CREATE,
        Capability.PROCUREMENT_ACCEPT,
        Capability.ACCESS_MANAGE_USERS,
        Capability.ACCESS_ASSIGN_STANDARD_ROLES,
        Capability.ACCESS_ASSIGN_ADMIN,
    },
}


def test_exact_role_capability_matrix() -> None:
    assert {
        role: frozenset(capabilities)
        for role, capabilities in EXPECTED.items()
    } == ROLE_CAPABILITIES


@pytest.mark.parametrize("role", list(UserRole))
def test_capability_serialization_is_deterministic(role: UserRole) -> None:
    serialized = serialized_capabilities(role)
    assert serialized == sorted(EXPECTED[role], key=str)
    assert len(serialized) == len(set(serialized))


def test_owner_does_not_receive_manager_procurement_workflow() -> None:
    assert Capability.PROCUREMENT_MANAGE not in ROLE_CAPABILITIES[UserRole.OWNER]


@pytest.mark.parametrize("role", list(UserRole))
def test_auth_state_serializes_backend_policy(role: UserRole) -> None:
    user = User(
        id=uuid.uuid4(),
        role=role,
        access_status=UserAccessStatus.APPROVED,
    )
    identity = TelegramIdentity(
        user=user,
        telegram_user_id=123,
        first_name="Test",
    )
    state = _state_response(
        user,
        identity,
        Settings(database_url="postgresql+asyncpg://unused"),
    )
    assert state.user.capabilities == sorted(EXPECTED[role], key=str)
