import {
  type RefObject,
} from "react";
import {
  Link,
} from "react-router-dom";

import {
  Button,
} from "../../shared/ui";
import {
  MovementAdminActions,
} from "./MovementAdminActions";
import {
  movementLabels,
  type Movement,
} from "../../shared/api/inventory";

export function MovementFeed({
  cursorDepth,
  displayedMovements,
  focusedMovementError,
  focusedMovementPending,
  hasNextPage,
  hasValidMovementLink,
  historyEmpty,
  historyError,
  historyPending,
  movementRef,
  requestedMovementId,
  onBackPage,
  onNextPage,
  onRetryHistory,
}: {
  cursorDepth: number;
  displayedMovements:
    readonly Movement[];
  focusedMovementError: boolean;
  focusedMovementPending: boolean;
  hasNextPage: boolean;
  hasValidMovementLink: boolean;
  historyEmpty: boolean;
  historyError: boolean;
  historyPending: boolean;
  movementRef:
    RefObject<HTMLElement | null>;
  requestedMovementId:
    string | null;
  onBackPage: () => void;
  onNextPage: () => void;
  onRetryHistory: () => void;
}) {
  return (
    <>
      {
        hasValidMovementLink
        && focusedMovementPending
          ? (
              <p role="status">
                Загружаем движение…
              </p>
            )
          : null
      }

      {
        hasValidMovementLink
        && focusedMovementError
          ? (
              <p role="alert">
                Движение не найдено
                или недоступно.
              </p>
            )
          : null
      }

      {
        !hasValidMovementLink
        && historyPending
          ? (
              <p role="status">
                Загружаем журнал…
              </p>
            )
          : null
      }

      {
        !hasValidMovementLink
        && historyError
          ? (
              <p role="alert">
                Не удалось загрузить журнал.{" "}
                <Button
                  onClick={onRetryHistory}
                >
                  Повторить
                </Button>
              </p>
            )
          : null
      }

      {
        !hasValidMovementLink
        && historyEmpty
          ? (
              <p>
                За выбранный период
                движений нет.
              </p>
            )
          : null
      }

      {displayedMovements.map(
        (movement) => {
          const focused =
            movement.id
            === requestedMovementId;

          return (
            <article
              className="movement-entry"
              key={movement.id}
              ref={
                focused
                  ? movementRef
                  : undefined
              }
              tabIndex={
                focused
                  ? -1
                  : undefined
              }
            >
              <header>
                <span>
                  № {
                    movement.journal_seq
                  }
                </span>
                <time
                  dateTime={
                    movement.occurred_at
                  }
                >
                  {
                    new Date(
                      movement
                        .occurred_at,
                    ).toLocaleString(
                      "ru-RU",
                    )
                  }
                </time>
              </header>

              <p>
                <strong>
                  {
                    movement
                      .actor_display_name_snapshot
                  }
                </strong>
                {" · "}
                {
                  movementLabels[
                    movement
                      .movement_type
                  ]
                }
              </p>

              <ul>
                {movement.lines.map(
                  (line) => (
                    <li key={line.id}>
                      {
                        line
                          .item_name_snapshot
                      }
                      {" — "}
                      <strong>
                        {
                          line.quantity
                        } шт.
                      </strong>
                    </li>
                  ),
                )}
              </ul>

              <p>
                {
                  movement
                    .source_location_name_snapshot
                    ? `Из: ${movement.source_location_name_snapshot}`
                    : ""
                }
                {
                  movement
                    .source_location_name_snapshot
                  && movement
                    .destination_location_name_snapshot
                    ? " → "
                    : ""
                }
                {
                  movement
                    .destination_location_name_snapshot
                    ? `В: ${movement.destination_location_name_snapshot}`
                    : ""
                }
              </p>

              <MovementAdminActions
                movement={movement}
              />

              {
                movement
                  .procurement_request_id
                  ? (
                      <Link
                        to={
                          `/procurement/${movement.procurement_request_id}`
                        }
                      >
                        Открыть закупку
                      </Link>
                    )
                  : null
              }
            </article>
          );
        },
      )}

      {!hasValidMovementLink ? (
        <div className="warehouse-actions">
          {cursorDepth > 1 ? (
            <Button
              className="button"
              onClick={onBackPage}
            >
              Назад
            </Button>
          ) : null}

          {hasNextPage ? (
            <Button
              className="button"
              onClick={onNextPage}
            >
              Следующая страница
            </Button>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
