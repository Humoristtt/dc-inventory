import {
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { useState } from "react";

import { useAuthState } from "../auth/useAuthState";
import { hasCapability } from "../../shared/api/auth";
import {
  createMovement,
  inventoryError,
  reverseMovement,
  type Movement,
  type MovementInput,
} from "../../shared/api/inventory";

type CorrectionDirection = "ADD" | "REMOVE";

type CorrectionDraft = {
  movement: Movement;
  locationId: string;
  direction: CorrectionDirection;
  quantities: Record<string, string>;
  clientRequestId: string;
};

type ReversalDraft = {
  movement: Movement;
  clientRequestId: string;
};

function newRequestId(prefix: string): string {
  return `${prefix}-${globalThis.crypto.randomUUID()}`;
}

function movementLocations(
  movement: Movement,
): Array<{ id: string; name: string }> {
  const result: Array<{ id: string; name: string }> = [];

  if (movement.source_location_id !== null) {
    result.push({
      id: movement.source_location_id,
      name:
        movement.source_location_name_snapshot
        ?? "Исходное место",
    });
  }

  if (
    movement.destination_location_id !== null
    && movement.destination_location_id
      !== movement.source_location_id
  ) {
    result.push({
      id: movement.destination_location_id,
      name:
        movement.destination_location_name_snapshot
        ?? "Целевое место",
    });
  }

  return result;
}

export function MovementAdminActions({
  movement,
}: {
  movement: Movement;
}) {
  const auth = useAuthState();
  const queryClient = useQueryClient();

  const [correction, setCorrection] =
    useState<CorrectionDraft | null>(null);
  const [reversal, setReversal] =
    useState<ReversalDraft | null>(null);
  const [validationError, setValidationError] =
    useState<string | null>(null);

  const canAdmin = hasCapability(
    auth.data?.user,
    "inventory.admin",
  );

  const availableLocations =
    movementLocations(movement);

  const canCorrect =
    canAdmin
    && movement.custody_user_id === null
    && movement.movement_type !== "CORRECTION"
    && movement.movement_type !== "REVERSAL"
    && availableLocations.length > 0;

  const canReverse =
    canAdmin
    && movement.movement_type !== "REVERSAL";

  const refreshWarehouse = () => {
    void queryClient.invalidateQueries({
      queryKey: ["inventory"],
    });
    void queryClient.invalidateQueries({
      queryKey: ["catalog"],
    });
  };

  const correctionMutation = useMutation({
    mutationFn: (payload: MovementInput) =>
      createMovement(payload),
    onSuccess: () => {
      refreshWarehouse();
      setCorrection(null);
      setValidationError(null);
    },
  });

  const reversalMutation = useMutation({
    mutationFn: (draft: ReversalDraft) =>
      reverseMovement(
        draft.movement.id,
        draft.clientRequestId,
      ),
    onSuccess: () => {
      refreshWarehouse();
      setReversal(null);
    },
  });

  if (!canCorrect && !canReverse) {
    return null;
  }

  const openCorrection = () => {
    correctionMutation.reset();
    setValidationError(null);

    setCorrection({
      movement,
      locationId: availableLocations[0]?.id ?? "",
      direction: "ADD",
      quantities: Object.fromEntries(
        movement.lines.map((line) => [
          line.id,
          "0",
        ]),
      ),
      clientRequestId:
        newRequestId("correction"),
    });
  };

  const closeCorrection = () => {
    correctionMutation.reset();
    setValidationError(null);
    setCorrection(null);
  };

  const submitCorrection = () => {
    if (correction === null) {
      return;
    }

    const lines: MovementInput["lines"] = [];

    for (const line of correction.movement.lines) {
      const raw =
        correction.quantities[line.id]?.trim()
        ?? "";

      if (raw === "" || raw === "0") {
        continue;
      }

      const quantity = Number(raw);

      if (
        !Number.isSafeInteger(quantity)
        || quantity <= 0
      ) {
        setValidationError(
          "Количество должно быть целым положительным числом.",
        );
        return;
      }

      lines.push({
        item_id: line.item_id,
        quantity,
      });
    }

    if (lines.length === 0) {
      setValidationError(
        "Укажите количество хотя бы для одной позиции.",
      );
      return;
    }

    if (correction.locationId === "") {
      setValidationError(
        "Выберите место хранения.",
      );
      return;
    }

    setValidationError(null);

    correctionMutation.mutate({
      movement_type: "CORRECTION",
      client_request_id:
        correction.clientRequestId,
      original_movement_id:
        correction.movement.id,
      source_location_id:
        correction.direction === "REMOVE"
          ? correction.locationId
          : undefined,
      destination_location_id:
        correction.direction === "ADD"
          ? correction.locationId
          : undefined,
      lines,
    });
  };

  const openReversal = () => {
    reversalMutation.reset();
    setReversal({
      movement,
      clientRequestId:
        newRequestId("reversal"),
    });
  };

  const closeReversal = () => {
    reversalMutation.reset();
    setReversal(null);
  };

  return (
    <>
      <div className="warehouse-actions">
        {canCorrect ? (
          <button
            className="button button--ghost"
            onClick={openCorrection}
            type="button"
          >
            Корректировать остаток
          </button>
        ) : null}

        {canReverse ? (
          <button
            className="button button--danger"
            onClick={openReversal}
            type="button"
          >
            Отменить операцию
          </button>
        ) : null}
      </div>

      {correction !== null ? (
        <div
          className="sheet-backdrop"
          role="presentation"
        >
          <section
            aria-labelledby="correction-title"
            aria-modal="true"
            className="sheet"
            role="dialog"
          >
            <header className="sheet__header">
              <div>
                <span className="section-kicker">
                  Корректировка
                </span>
                <h2 id="correction-title">
                  Скорректировать остаток
                </h2>
              </div>

              <button
                aria-label="Закрыть корректировку"
                className="icon-button"
                data-escape-dismiss=""
                disabled={
                  correctionMutation.isPending
                }
                onClick={closeCorrection}
                type="button"
              >
                ×
              </button>
            </header>

            <div className="sheet__body">
              <p>
                Исходная операция №{" "}
                {correction.movement.journal_seq}.
                Корректировка создаст новое
                движение и не изменит историю.
              </p>

              <label>
                Изменение остатка
                <select
                  value={correction.direction}
                  onChange={(event) =>
                    setCorrection((current) =>
                      current === null
                        ? current
                        : {
                            ...current,
                            direction:
                              event.target.value as CorrectionDirection,
                          },
                    )
                  }
                >
                  <option value="ADD">
                    Увеличить остаток
                  </option>
                  <option value="REMOVE">
                    Уменьшить остаток
                  </option>
                </select>
              </label>

              {availableLocations.length > 1 ? (
                <label>
                  Место хранения
                  <select
                    value={correction.locationId}
                    onChange={(event) =>
                      setCorrection((current) =>
                        current === null
                          ? current
                          : {
                              ...current,
                              locationId:
                                event.target.value,
                            },
                      )
                    }
                  >
                    {availableLocations.map(
                      (location) => (
                        <option
                          key={location.id}
                          value={location.id}
                        >
                          {location.name}
                        </option>
                      ),
                    )}
                  </select>
                </label>
              ) : (
                <p>
                  Место:{" "}
                  <strong>
                    {
                      availableLocations[0]
                        ?.name
                    }
                  </strong>
                </p>
              )}

              {correction.movement.lines.map(
                (line) => (
                  <label key={line.id}>
                    Количество:{" "}
                    {line.item_name_snapshot}
                    <input
                      inputMode="numeric"
                      min="0"
                      step="1"
                      type="number"
                      value={
                        correction.quantities[
                          line.id
                        ] ?? "0"
                      }
                      onChange={(event) =>
                        setCorrection(
                          (current) =>
                            current === null
                              ? current
                              : {
                                  ...current,
                                  quantities: {
                                    ...current.quantities,
                                    [line.id]:
                                      event
                                        .target
                                        .value,
                                  },
                                },
                        )
                      }
                    />
                  </label>
                ),
              )}

              {validationError !== null ? (
                <p role="alert">
                  {validationError}
                </p>
              ) : null}

              {correctionMutation.isError ? (
                <p role="alert">
                  {inventoryError(
                    correctionMutation.error,
                  )}
                </p>
              ) : null}
            </div>

            <footer className="sheet__footer">
              <button
                className="button button--ghost"
                disabled={
                  correctionMutation.isPending
                }
                onClick={closeCorrection}
                type="button"
              >
                Отмена
              </button>

              <button
                className="button button--dark"
                disabled={
                  correctionMutation.isPending
                }
                onClick={submitCorrection}
                type="button"
              >
                {correctionMutation.isPending
                  ? "Сохраняем…"
                  : "Создать корректировку"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}

      {reversal !== null ? (
        <div
          className="sheet-backdrop"
          role="presentation"
        >
          <section
            aria-labelledby="reversal-title"
            aria-modal="true"
            className="sheet"
            role="dialog"
          >
            <header className="sheet__header">
              <div>
                <span className="section-kicker">
                  Необратимое действие
                </span>
                <h2 id="reversal-title">
                  Отменить операцию №{" "}
                  {reversal.movement.journal_seq}?
                </h2>
              </div>

              <button
                aria-label="Закрыть отмену операции"
                className="icon-button"
                data-escape-dismiss=""
                disabled={
                  reversalMutation.isPending
                }
                onClick={closeReversal}
                type="button"
              >
                ×
              </button>
            </header>

            <div className="sheet__body">
              <p>
                Исходное движение останется в
                журнале. Система создаст отдельное
                обратное движение REVERSAL.
              </p>

              {reversalMutation.isError ? (
                <p role="alert">
                  {inventoryError(
                    reversalMutation.error,
                  )}
                </p>
              ) : null}
            </div>

            <footer className="sheet__footer">
              <button
                className="button button--ghost"
                disabled={
                  reversalMutation.isPending
                }
                onClick={closeReversal}
                type="button"
              >
                Не отменять
              </button>

              <button
                className="button button--danger"
                disabled={
                  reversalMutation.isPending
                }
                onClick={() =>
                  reversalMutation.mutate(
                    reversal,
                  )
                }
                type="button"
              >
                {reversalMutation.isPending
                  ? "Отменяем…"
                  : "Создать отмену"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </>
  );
}
