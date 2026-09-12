from enum import StrEnum

from app.modules.identity.enums import UserRole


class Capability(StrEnum):
    CATALOG_READ = "catalog.read"
    CATALOG_MANAGE = "catalog.manage"
    CATALOG_ARCHIVE = "catalog.archive"
    CATALOG_DELETE_UNUSED = "catalog.delete_unused"
    INVENTORY_READ = "inventory.read"
    INVENTORY_OPERATE = "inventory.operate"
    INVENTORY_ADMIN = "inventory.admin"
    MOVEMENT_READ_OWN = "movement.read_own"
    MOVEMENT_READ_ALL = "movement.read_all"
    PROCUREMENT_READ = "procurement.read"
    PROCUREMENT_CREATE = "procurement.create"
    PROCUREMENT_MANAGE = "procurement.manage"
    PROCUREMENT_ACCEPT = "procurement.accept"
    ACCESS_MANAGE_USERS = "access.manage_users"
    ACCESS_ASSIGN_STANDARD_ROLES = "access.assign_standard_roles"
    ACCESS_ASSIGN_ADMIN = "access.assign_admin"


ENGINEER_CAPABILITIES = frozenset(
    {
        Capability.CATALOG_READ,
        Capability.INVENTORY_READ,
        Capability.INVENTORY_OPERATE,
        Capability.MOVEMENT_READ_OWN,
    }
)

ROLE_CAPABILITIES: dict[UserRole, frozenset[Capability]] = {
    UserRole.ENGINEER: ENGINEER_CAPABILITIES,
    UserRole.SENIOR_ENGINEER: ENGINEER_CAPABILITIES
    | {
        Capability.CATALOG_MANAGE,
        Capability.CATALOG_ARCHIVE,
        Capability.CATALOG_DELETE_UNUSED,
        Capability.MOVEMENT_READ_ALL,
        Capability.PROCUREMENT_READ,
        Capability.PROCUREMENT_ACCEPT,
    },
    UserRole.MANAGER: frozenset(
        {
            Capability.CATALOG_READ,
            Capability.INVENTORY_READ,
            Capability.PROCUREMENT_READ,
            Capability.PROCUREMENT_MANAGE,
        }
    ),
    UserRole.ADMIN: frozenset(
        {
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
        }
    ),
    UserRole.OWNER: frozenset(
        {
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
        }
    ),
}

STANDARD_ASSIGNABLE_ROLES = frozenset(
    {UserRole.ENGINEER, UserRole.SENIOR_ENGINEER, UserRole.MANAGER}
)
CUSTODY_ROLES = frozenset(
    {UserRole.ENGINEER, UserRole.SENIOR_ENGINEER}
)

# Ordinary identity mutations hold this barrier in shared mode.
# Recovery OWNER rotation holds it exclusively.
IDENTITY_MANAGEMENT_LOCK_KEY = 4937638921054812071


def capabilities_for_role(role: UserRole) -> frozenset[Capability]:
    return ROLE_CAPABILITIES[role]


def has_capability(role: UserRole, capability: Capability) -> bool:
    return capability in capabilities_for_role(role)


def serialized_capabilities(role: UserRole) -> list[Capability]:
    return sorted(capabilities_for_role(role), key=str)
