import {
  Link,
} from "react-router-dom";

import {
  Button,
} from "../../shared/ui";
import type {
  ProcurementEvent,
  ProcurementRequest,
} from "../../shared/api/procurement";
import {
  procurementLineTitle,
} from "./procurementDetailModel";

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
