import {
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import {
  decideAdminUserAccessRequest,
  setAdminUserAccess,
  setAdminUserRole,
  type AdminAccessRequestDecision,
} from "../../shared/api/adminUsers";
import type {
  UserAccessStatus,
  UserRole,
} from "../../shared/api/auth";

export function useAdminUserMutations() {
  const queryClient =
    useQueryClient();

  const accessMutation = useMutation({
    mutationFn: ({
      userId,
      accessStatus,
    }: {
      userId: string;
      accessStatus:
        UserAccessStatus;
    }) =>
      setAdminUserAccess(
        userId,
        accessStatus,
      ),

    onSuccess:
      async (_, variables) => {
        await queryClient
          .invalidateQueries({
            queryKey: [
              "admin",
              "users",
            ],
          });

        await queryClient
          .invalidateQueries({
            queryKey: [
              "admin",
              "user-access-events",
              variables.userId,
            ],
          });
      },
  });

  const accessDecisionMutation =
    useMutation({
      mutationFn: ({
        userId,
        decision,
      }: {
        userId: string;
        decision:
          AdminAccessRequestDecision;
      }) =>
        decideAdminUserAccessRequest(
          userId,
          decision,
        ),

      onSuccess:
        async (_, variables) => {
          await queryClient
            .invalidateQueries({
              queryKey: [
                "admin",
                "users",
              ],
            });

          await queryClient
            .invalidateQueries({
              queryKey: [
                "admin",
                "user-access-events",
                variables.userId,
              ],
            });
        },
    });

  const roleMutation = useMutation({
    mutationFn: ({
      userId,
      role,
    }: {
      userId: string;
      role: UserRole;
    }) =>
      setAdminUserRole(
        userId,
        role,
      ),

    onSuccess:
      async (_, variables) => {
        await queryClient
          .invalidateQueries({
            queryKey: [
              "admin",
              "users",
            ],
          });

        await queryClient
          .invalidateQueries({
            queryKey: [
              "admin",
              "user-role-events",
              variables.userId,
            ],
          });
      },
  });

  return {
    accessDecisionMutation,
    accessMutation,
    roleMutation,
  };
}
