import type {
  AdminUser,
} from "../../shared/api/adminUsers";
import type {
  UserRole,
} from "../../shared/api/auth";

export type AdminTargetPolicyContext = {
  currentUserId:
    | string
    | undefined;
  canAssignAdmin: boolean;
  assignableRoles:
    readonly UserRole[];
};

export function canDecidePendingAccess(
  user: AdminUser,
  {
    currentUserId,
    canAssignAdmin,
  }: AdminTargetPolicyContext,
): boolean {
  if (
    user.access_status !== "PENDING"
    || user.id === currentUserId
    || user.role === "OWNER"
  ) {
    return false;
  }

  return !(
    user.role === "ADMIN"
    && !canAssignAdmin
  );
}

export function canManageTargetAccess(
  user: AdminUser,
  {
    currentUserId,
    canAssignAdmin,
  }: AdminTargetPolicyContext,
): boolean {
  if (
    user.id === currentUserId
    || user.role === "OWNER"
  ) {
    return false;
  }

  if (
    user.role === "ADMIN"
    && !canAssignAdmin
  ) {
    return false;
  }

  return (
    user.access_status === "APPROVED"
    || user.access_status === "BLOCKED"
  );
}

export function canManageTargetRole(
  user: AdminUser,
  {
    currentUserId,
    canAssignAdmin,
    assignableRoles,
  }: AdminTargetPolicyContext,
): boolean {
  if (
    user.id === currentUserId
    || user.role === "OWNER"
    || assignableRoles.length === 0
  ) {
    return false;
  }

  return !(
    user.role === "ADMIN"
    && !canAssignAdmin
  );
}
