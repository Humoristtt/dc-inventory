import type {
  AdminUser,
} from "../../shared/api/adminUsers";
import type {
  UserAccessStatus,
  UserRole,
} from "../../shared/api/auth";

export const ACCESS_LABELS:
  Record<UserAccessStatus, string> = {
    PENDING: "Ожидает подтверждения",
    APPROVED: "Доступ разрешён",
    REJECTED: "Запрос отклонён",
    BLOCKED: "Заблокирован",
  };

export const STANDARD_ASSIGNABLE_ROLES:
  readonly UserRole[] = [
    "ENGINEER",
    "SENIOR_ENGINEER",
    "MANAGER",
  ];

export const USERS_PAGE_SIZE = 50;
export const HISTORY_PAGE_SIZE = 20;

export function displayAdminUserName(
  user: AdminUser,
): string {
  const fullName = [
    user.first_name,
    user.last_name,
  ]
    .filter(Boolean)
    .join(" ");

  return user.username
    ? `${fullName} · @${user.username}`
    : fullName;
}
