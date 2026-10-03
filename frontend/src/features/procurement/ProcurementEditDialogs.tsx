import {
  Button,
  Textarea,
} from "../../shared/ui";
import type {
  ProcurementLineInput,
} from "../../shared/api/procurement";
import {
  LineComposer,
} from "./LineComposer";
import {
  ProcurementDialog,
} from "./ProcurementDialog";
import type {
  ProcurementDialogKind,
} from "./ProcurementActionBar";
import type {
  ProcurementAction,
} from "./procurementDetailDialogTypes";

export function ProcurementEditDialogs({
  comment,
  dialog,
  mutationPending,
  proposal,
  revisionLines,
  onAction,
  onClose,
  onCommentChange,
  onProposalChange,
  onRevisionLinesChange,
}: {
  comment: string;
  dialog:
    | ProcurementDialogKind
    | null;
  mutationPending: boolean;
  proposal:
    ProcurementLineInput[];
  revisionLines:
    ProcurementLineInput[];
  onAction: ProcurementAction;
  onClose: () => void;
  onCommentChange:
    (value: string) => void;
  onProposalChange:
    (lines:
      ProcurementLineInput[],
    ) => void;
  onRevisionLinesChange:
    (lines:
      ProcurementLineInput[],
    ) => void;
}) {
  return (
    <>
      <ProcurementDialog
        onClose={onClose}
        open={
          dialog === "correction"
        }
        title="Вернуть на корректировку"
      >
        <label>
          Комментарий
          <Textarea
            maxLength={4000}
            onChange={(event) =>
              onCommentChange(
                event.target.value,
              )
            }
            value={comment}
          />
        </label>

        <details>
          <summary>
            Добавить альтернативный
            состав
          </summary>
          <LineComposer
            lines={proposal}
            onChange={
              onProposalChange
            }
          />
        </details>

        <Button
          className="button button--danger"
          disabled={
            !comment.trim()
            || mutationPending
          }
          onClick={() =>
            onAction(
              "return-for-correction",
              {
                comment,
                alternative_proposal:
                  proposal.length
                    ? proposal
                    : null,
              },
            )
          }
        >
          Вернуть
        </Button>
      </ProcurementDialog>

      <ProcurementDialog
        onClose={onClose}
        open={
          dialog === "revision"
        }
        title="Новая редакция"
      >
        <LineComposer
          lines={revisionLines}
          onChange={
            onRevisionLinesChange
          }
        />

        <label>
          Комментарий
          <Textarea
            maxLength={4000}
            onChange={(event) =>
              onCommentChange(
                event.target.value,
              )
            }
            value={comment}
          />
        </label>

        <Button
          className="button button--accent"
          disabled={
            !revisionLines.length
            || mutationPending
          }
          onClick={() =>
            onAction(
              "revisions",
              {
                lines:
                  revisionLines,
                general_comment:
                  comment.trim()
                  || null,
              },
            )
          }
        >
          Отправить редакцию
        </Button>
      </ProcurementDialog>

      <ProcurementDialog
        onClose={onClose}
        open={
          dialog === "discrepancy"
        }
        title="Есть расхождения"
      >
        <label>
          Что отличается
          <Textarea
            maxLength={4000}
            onChange={(event) =>
              onCommentChange(
                event.target.value,
              )
            }
            value={comment}
          />
        </label>

        <Button
          className="button button--danger"
          disabled={
            !comment.trim()
            || mutationPending
          }
          onClick={() =>
            onAction(
              "discrepancies",
              { comment },
            )
          }
        >
          Зафиксировать
        </Button>
      </ProcurementDialog>
    </>
  );
}
