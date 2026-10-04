import {
  Button,
} from "../../shared/ui";
import type {
  ProcurementRequest,
} from "../../shared/api/procurement";

export type ProcurementDialogKind =
  | "correction"
  | "revision"
  | "transfer"
  | "discrepancy"
  | "accept";

export function ProcurementActionBar({
  request,
  actions,
  mutationPending,
  onAction,
  onOpenDialog,
  onOpenRevision,
}: {
  request: ProcurementRequest;
  actions: ReadonlySet<string>;
  mutationPending: boolean;
  onAction: (
    action: string,
    extra?:
      Record<string, unknown>,
  ) => void;
  onOpenDialog: (
    dialog:
      ProcurementDialogKind,
  ) => void;
  onOpenRevision: () => void;
}) {
  return (
    <div className="procurement-actions">
      {
        actions.has(
          "take_ownership",
        )
          ? (
              <Button
                className="button"
                disabled={
                  mutationPending
                }
                onClick={() =>
                  onAction(
                    "take-ownership",
                    {
                      expected_assigned_manager_user_id:
                        request
                          .assigned_manager
                          .id,
                    },
                  )
                }
              >
                Взять на себя
              </Button>
            )
          : null
      }

      {
        actions.has(
          "transfer_manager",
        )
          ? (
              <Button
                className="button"
                disabled={
                  mutationPending
                }
                onClick={() =>
                  onOpenDialog(
                    "transfer",
                  )
                }
              >
                Передать менеджеру
              </Button>
            )
          : null
      }

      {
        actions.has(
          "manager_accept",
        )
          ? (
              <Button
                className="button button--dark"
                disabled={
                  mutationPending
                }
                onClick={() =>
                  onAction(
                    "manager-accept",
                  )
                }
              >
                Принять в работу
              </Button>
            )
          : null
      }

      {
        actions.has(
          "return_for_correction",
        )
          ? (
              <Button
                className="button button--danger"
                disabled={
                  mutationPending
                }
                onClick={() =>
                  onOpenDialog(
                    "correction",
                  )
                }
              >
                Вернуть на корректировку
              </Button>
            )
          : null
      }

      {
        actions.has(
          "transfer_to_acceptance",
        )
          ? (
              <Button
                className="button button--dark"
                disabled={
                  mutationPending
                }
                onClick={() =>
                  onAction(
                    "transfer-to-acceptance",
                  )
                }
              >
                Передать на приёмку
              </Button>
            )
          : null
      }

      {
        actions.has(
          "submit_revision",
        )
          ? (
              <Button
                className="button button--accent"
                disabled={
                  mutationPending
                }
                onClick={
                  onOpenRevision
                }
              >
                Создать новую редакцию
              </Button>
            )
          : null
      }

      {
        actions.has(
          "report_discrepancy",
        )
          ? (
              <Button
                className="button button--danger"
                disabled={
                  mutationPending
                }
                onClick={() =>
                  onOpenDialog(
                    "discrepancy",
                  )
                }
              >
                Есть расхождения
              </Button>
            )
          : null
      }

      {
        actions.has(
          "complete_acceptance",
        )
          ? (
              <Button
                className="button button--accent"
                disabled={
                  mutationPending
                }
                onClick={() =>
                  onOpenDialog(
                    "accept",
                  )
                }
              >
                Подтвердить приёмку
              </Button>
            )
          : null
      }
    </div>
  );
}

