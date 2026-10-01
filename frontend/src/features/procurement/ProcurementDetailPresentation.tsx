import {
  Link,
} from "react-router-dom";

import {
  Button,
} from "../../shared/ui";
import type {
  ProcurementEvent,
  ProcurementLine,
  ProcurementLineInput,
  ProcurementRequest,
} from "../../shared/api/procurement";

const EVENT_LABELS:
  Record<string, string> = {
    REQUEST_CREATED:
      "Заявка создана",
    REVISION_SUBMITTED:
      "Отправлена новая редакция",
    MANAGER_ACCEPTED:
      "Менеджер принял в работу",
    CORRECTION_REQUESTED:
      "Возвращено на корректировку",
    ASSIGNMENT_TAKEN:
      "Менеджер взял заявку на себя",
    ASSIGNMENT_TRANSFERRED:
      "Назначен другой менеджер",
    TRANSFERRED_TO_ACCEPTANCE:
      "Передано на приёмку",
    LINE_BOUND:
      "Позиция связана с каталогом",
    DISCREPANCY_REPORTED:
      "Зафиксированы расхождения",
    COMPLETED:
      "Приёмка завершена",
  };

export function procurementLineTitle(
  line: ProcurementLine,
): string {
  return [
    line.display_snapshot
      .manufacturer_name,
    line.display_snapshot.name,
    line.display_snapshot.model,
  ]
    .filter(
      (
        value,
      ): value is string =>
        typeof value === "string"
        && Boolean(value),
    )
    .join(" · ");
}

export function procurementInputFromLine(
  line: ProcurementLine,
): ProcurementLineInput {
  if (
    line.line_type
      === "EXISTING_ITEM"
    && line.catalog_item_id
  ) {
    return {
      line_type: "EXISTING_ITEM",
      item_id:
        line.catalog_item_id,
      display_name:
        procurementLineTitle(
          line,
        ),
      quantity: line.quantity,
    };
  }

  const snapshot =
    line.display_snapshot;

  return {
    line_type: "PROPOSED_ITEM",
    category_key:
      String(
        snapshot.category_key
        ?? "",
      ),
    manufacturer_id:
      typeof snapshot
        .manufacturer_id
        === "string"
        ? snapshot
            .manufacturer_id
        : null,
    name:
      String(
        snapshot.name ?? "",
      ),
    model:
      typeof snapshot.model
        === "string"
        ? snapshot.model
        : null,
    attributes: (
      snapshot.attributes ?? {}
    ) as Record<
      string,
      | string
      | number
      | boolean
    >,
    quantity: line.quantity,
  };
}

export function ProcurementOverview({
  request,
  canReadMovements,
}: {
  request: ProcurementRequest;
  canReadMovements: boolean;
}) {
  return (
    <section className="detail-panel procurement-overview">
      <div>
        <span>Инициатор</span>
        <strong>
          {
            request.initiator
              .display_name
          }
        </strong>
      </div>
      <div>
        <span>Менеджер</span>
        <strong>
          {
            request
              .assigned_manager
              .display_name
          }
        </strong>
      </div>
      <div>
        <span>Редакция</span>
        <strong>
          № {
            request
              .revision_number
          }
        </strong>
      </div>

      {
        request.final_movement_id
        && canReadMovements
          ? (
              <Link
                to={
                  `/movements?movement=${request.final_movement_id}`
                }
              >
                Открыть складской приход
              </Link>
            )
          : null
      }
    </section>
  );
}

export function ProcurementCurrentLines({
  request,
  actions,
  mutationPending,
  onBindLine,
}: {
  request: ProcurementRequest;
  actions: ReadonlySet<string>;
  mutationPending: boolean;
  onBindLine: (
    lineId: string,
  ) => void;
}) {
  return (
    <section className="detail-panel">
      <h2>Текущий состав</h2>

      <ol className="procurement-lines procurement-lines--detail">
        {
          request
            .current_revision
            .lines
            .map(
              (line) => (
                <li key={line.id}>
                  <div>
                    <strong>
                      {
                        procurementLineTitle(
                          line,
                        )
                      }
                    </strong>
                    <span>
                      {line.quantity} шт.
                    </span>

                    {
                      line.line_type
                        === "PROPOSED_ITEM"
                        ? (
                            <small>
                              {
                                line.bound_item_id
                                  ? "Связана с каталогом"
                                  : "Нужна карточка каталога"
                              }
                            </small>
                          )
                        : null
                    }
                  </div>

                  {
                    actions.has(
                      "bind_lines",
                    )
                    && !line.bound_item_id
                      ? (
                          <div className="procurement-line-actions">
                            <Button
                              className="button"
                              disabled={
                                mutationPending
                              }
                              onClick={() =>
                                onBindLine(
                                  line.id,
                                )
                              }
                            >
                              Связать
                            </Button>

                            <Link
                              className="button button--accent"
                              to={
                                `/catalog/new?procurementRequestId=${request.id}&procurementLineId=${line.id}`
                              }
                            >
                              Создать карточку
                            </Link>
                          </div>
                        )
                      : null
                  }
                </li>
              ),
            )
        }
      </ol>

      {
        request
          .current_revision
          .general_comment
          ? (
              <p>
                {
                  request
                    .current_revision
                    .general_comment
                }
              </p>
            )
          : null
      }
    </section>
  );
}

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

export function ProcurementHistory({
  events,
}: {
  events:
    readonly ProcurementEvent[];
}) {
  return (
    <section className="detail-panel">
      <h2>История</h2>

      <ol className="procurement-timeline">
        {
          [...events]
            .reverse()
            .map(
              (event) => (
                <li key={event.id}>
                  <strong>
                    {
                      EVENT_LABELS[
                        event.event_type
                      ]
                      ?? event.event_type
                    }
                  </strong>
                  <span>
                    {
                      event.actor
                        .display_name
                    }
                    {" · "}
                    {
                      new Date(
                        event.occurred_at,
                      ).toLocaleString(
                        "ru-RU",
                      )
                    }
                  </span>

                  {
                    event.comment
                      ? (
                          <p>
                            {
                              event.comment
                            }
                          </p>
                        )
                      : null
                  }

                  {
                    Array.isArray(
                      event.metadata
                        ?.alternative_proposal,
                    )
                      ? (
                          <p>
                            Альтернативное
                            предложение:{" "}
                            {
                              event.metadata
                                ?.alternative_proposal
                                .length
                            } поз.
                          </p>
                        )
                      : null
                  }
                </li>
              ),
            )
        }
      </ol>
    </section>
  );
}

export function ProcurementRevisions({
  request,
}: {
  request: ProcurementRequest;
}) {
  return (
    <section className="detail-panel">
      <h2>Редакции</h2>

      {
        request.revisions.map(
          (revision) => (
            <details
              key={revision.id}
              open={
                revision.id
                === request
                  .current_revision_id
              }
            >
              <summary>
                Редакция №{
                  revision.revision_number
                }
                {" · "}
                {
                  revision.lines.length
                } поз.
              </summary>

              <ul>
                {
                  revision.lines.map(
                    (line) => (
                      <li key={line.id}>
                        {
                          procurementLineTitle(
                            line,
                          )
                        }
                        {" — "}
                        {line.quantity} шт.
                      </li>
                    ),
                  )
                }
              </ul>
            </details>
          ),
        )
      }
    </section>
  );
}
