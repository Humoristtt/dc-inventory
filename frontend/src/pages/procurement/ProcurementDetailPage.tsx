import { Button, Input, Select, Textarea } from "../../shared/ui";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { LineComposer } from "../../features/procurement/LineComposer";
import { useAuthState } from "../../features/auth/useAuthState";
import { getCatalogItems } from "../../shared/api/catalog";
import { getLocations } from "../../shared/api/inventory";
import {
  getProcurementManagers,
  getProcurementRequest,
  mutateProcurement,
  procurementError,
  procurementLinesPayload,
  type ProcurementLineInput,
} from "../../shared/api/procurement";
import {
  ProcurementActionBar,
  ProcurementCurrentLines,
  ProcurementHistory,
  ProcurementOverview,
  ProcurementRevisions,
  procurementInputFromLine,
  procurementLineTitle,
  type ProcurementDialogKind,
} from "../../features/procurement/ProcurementDetailPresentation";
import { PageHeader } from "../../shared/ui";
import "../../features/procurement/procurement.css";

function Dialog({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;

    const previousFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const dialogElement = dialogRef.current;
    const focusableSelector =
      'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

    const firstFocusable =
      dialogElement?.querySelector<HTMLElement>(focusableSelector);

    if (firstFocusable) {
      firstFocusable.focus();
    } else {
      dialogElement?.focus();
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }

      if (event.key !== "Tab" || !dialogElement) return;

      const focusables = Array.from(
        dialogElement.querySelectorAll<HTMLElement>(focusableSelector),
      );
      const first = focusables[0];
      const last = focusables.at(-1);

      if (!first || !last) {
        event.preventDefault();
        dialogElement.focus();
        return;
      }

      if (!dialogElement.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
        return;
      }

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      previousFocus?.focus();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="procurement-dialog-backdrop"
      role="presentation"
      onMouseDown={onClose}
    >
      <section
        aria-labelledby={titleId}
        aria-modal="true"
        className="procurement-dialog form-surface"
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="procurement-dialog__heading">
          <h2 id={titleId}>{title}</h2>
          <Button
            aria-label="Закрыть"
            onClick={onClose}
            type="button"
          >
            ×
          </Button>
        </div>
        {children}
      </section>
    </div>
  );
}

export function ProcurementDetailPage() {
  const { requestId = "" } = useParams();
  const auth = useAuthState();
  const canReadProcurement =
    auth.data?.user.capabilities.includes("procurement.read") ?? false;
  const canReadMovements =
    auth.data?.user.capabilities.some(
      (capability) =>
        capability === "movement.read_own"
        || capability === "movement.read_all",
    ) ?? false;
  const queryClient = useQueryClient();
  const request = useQuery({
    queryKey: ["procurement", "request", requestId],
    queryFn: ({ signal }) => getProcurementRequest(requestId, signal),
    enabled:
      Boolean(requestId)
      && !auth.isPending
      && canReadProcurement,
  });
  const [managerSearch, setManagerSearch] = useState("");

  const managers = useInfiniteQuery({
    queryKey: [
      "procurement",
      "managers",
      "transfer",
      managerSearch,
    ],
    queryFn: ({ pageParam, signal }) =>
      getProcurementManagers(
        {
          q: managerSearch,
          limit: 50,
          offset: pageParam,
        },
        signal,
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const nextOffset =
        lastPage.offset
        + lastPage.items.length;

      return nextOffset < lastPage.total
        ? nextOffset
        : undefined;
    },
    enabled: Boolean(
      request.data?.available_actions.includes(
        "transfer_manager",
      ),
    ),
  });

  const managerOptions =
    managers.data?.pages.flatMap(
      (page) => page.items,
    )
    ?? [];
  const locations = useQuery({
    queryKey: ["inventory", "locations"],
    queryFn: ({ signal }) => getLocations(signal),
    enabled: Boolean(request.data?.available_actions.includes("complete_acceptance")),
  });
  const [dialog, setDialog] = useState<ProcurementDialogKind | null>(null);
  const [comment, setComment] = useState("");
  const [proposal, setProposal] = useState<ProcurementLineInput[]>([]);
  const [revisionLines, setRevisionLines] = useState<ProcurementLineInput[]>([]);
  const [managerId, setManagerId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [bindingLine, setBindingLine] = useState<string | null>(null);
  const [bindingSearch, setBindingSearch] = useState("");

  const bindingItems = useInfiniteQuery({
    queryKey: [
      "catalog",
      "procurement-binding",
      bindingSearch,
    ],
    queryFn: ({ pageParam, signal }) =>
      getCatalogItems(
        {
          q: bindingSearch,
          limit: 20,
          offset: pageParam,
        },
        signal,
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const nextOffset =
        lastPage.offset
        + lastPage.items.length;

      return nextOffset < lastPage.total
        ? nextOffset
        : undefined;
    },
    enabled:
      bindingLine !== null
      && bindingSearch.trim().length >= 2,
  });

  const bindingItemOptions =
    bindingItems.data?.pages.flatMap(
      (page) => page.items,
    )
    ?? [];
  const actionIntentRef = useRef<{
    fingerprint: string;
    clientRequestId: string;
  } | null>(null);
  const mutationInFlightRef = useRef(false);

  const mutation = useMutation({
    mutationFn: ({ action, body }: { action: string; body: Record<string, unknown> }) =>
      mutateProcurement(requestId, action, body),
    onSuccess: (saved) => {
      actionIntentRef.current = null;
      queryClient.setQueryData(["procurement", "request", requestId], saved);
      void queryClient.invalidateQueries({ queryKey: ["procurement", "requests"] });
      setDialog(null);
      setBindingLine(null);
      setComment("");
    },
    onError: async () => {
      await request.refetch();
    },
    onSettled: () => {
      mutationInFlightRef.current = false;
    },
  });

  const current = request.data;
  const actions = useMemo(() => new Set(current?.available_actions ?? []), [current]);
  const activeLocations =
    locations.data?.filter((entry) => entry.status === "ACTIVE") ?? [];
  const act = (action: string, extra: Record<string, unknown> = {}) => {
    if (!current || mutationInFlightRef.current) return;

    const command: Record<string, unknown> = {
      expected_state_version: current.state_version,
      expected_revision_id: current.current_revision_id,
      ...extra,
    };
    if (Array.isArray(command.lines)) {
      command.lines = procurementLinesPayload(
        command.lines as ProcurementLineInput[],
      );
    }
    if (Array.isArray(command.alternative_proposal)) {
      command.alternative_proposal = procurementLinesPayload(
        command.alternative_proposal as ProcurementLineInput[],
      );
    }

    const fingerprint = JSON.stringify([action, command]);
    let intent = actionIntentRef.current;
    if (
      intent === null
      || intent.fingerprint !== fingerprint
    ) {
      intent = {
        fingerprint,
        clientRequestId: crypto.randomUUID(),
      };
      actionIntentRef.current = intent;
    }

    mutationInFlightRef.current = true;
    mutation.mutate({
      action,
      body: {
        ...command,
        client_request_id: intent.clientRequestId,
      },
    });
  };

  if (auth.isPending || request.isPending) return <p role="status">Загрузка…</p>;
  if (!canReadProcurement) {
    return <Navigate replace to="/catalog" />;
  }
  if (request.isError || !current) {
    return (
      <p role="alert">
        Не удалось открыть закупку.{" "}
        <Button onClick={() => void request.refetch()} type="button">Повторить</Button>
      </p>
    );
  }

  const openRevision = () => {
    setRevisionLines(
      current.current_revision.lines.map(
        procurementInputFromLine,
      ),
    );
    setDialog("revision");
  };

  return (
    <main className="procurement-page">
      <PageHeader kicker="Закупка" title={current.request_number} description={current.status_label} />
      <div className="procurement-page__body">
        <ProcurementOverview
          canReadMovements={
            canReadMovements
          }
          request={current}
        />

        <ProcurementCurrentLines
          actions={actions}
          mutationPending={
            mutation.isPending
          }
          onBindLine={
            setBindingLine
          }
          request={current}
        />

        <ProcurementActionBar
          actions={actions}
          mutationPending={
            mutation.isPending
          }
          onAction={act}
          onOpenDialog={
            setDialog
          }
          onOpenRevision={
            openRevision
          }
          request={current}
        />

        {mutation.isPending ? (
          <p role="status">
            Сохраняем…
          </p>
        ) : null}

        {mutation.isError ? (
          <p role="alert">
            {
              procurementError(
                mutation.error,
              )
            }
          </p>
        ) : null}

        <ProcurementHistory
          events={current.events}
        />

        <ProcurementRevisions
          request={current}
        />
      </div>

      <Dialog
        open={dialog === "transfer"}
        title="Передать менеджеру"
        onClose={() => setDialog(null)}
      >
        <label>
          Поиск менеджера
          <Input
            value={managerSearch}
            onChange={(event) => {
              setManagerSearch(
                event.target.value,
              );
              setManagerId("");
            }}
          />
        </label>

        {managers.isPending ? (
          <p role="status">Загружаем менеджеров…</p>
        ) : null}
        {managers.isError ? (
          <p role="alert">
            Не удалось загрузить менеджеров.{" "}
            <Button
              onClick={() => void managers.refetch()}
              type="button"
            >
              Повторить
            </Button>
          </p>
        ) : null}
        {!managers.isPending
          && !managers.isError
          && managerOptions.length === 0 ? (
            <p>Менеджеры не найдены.</p>
          ) : null}

        <label>
          Новый менеджер
          <Select
            disabled={
              managers.isPending
              || managers.isError
              || mutation.isPending
            }
            value={managerId}
            onChange={(event) =>
              setManagerId(
                event.target.value,
              )}
          >
            <option value="">
              Выберите
            </option>
            {managerOptions
              .filter(
                (entry) =>
                  entry.id
                  !== current.assigned_manager.id,
              )
              .map((entry) => (
                <option
                  key={entry.id}
                  value={entry.id}
                >
                  {entry.display_name}
                </option>
              ))}
          </Select>
        </label>

        {managers.hasNextPage ? (
          <Button
            className="button button--load-more"
            disabled={
              managers.isFetchingNextPage
            }
            onClick={() =>
              void managers.fetchNextPage()
            }
            type="button"
          >
            {managers.isFetchingNextPage
              ? "Загружаем менеджеров…"
              : "Показать ещё менеджеров"}
          </Button>
        ) : null}

        <Button
          className="button button--dark"
          disabled={
            !managerId
            || managers.isError
            || mutation.isPending
          }
          onClick={() =>
            act(
              "transfer-manager",
              {
                expected_assigned_manager_user_id:
                  current.assigned_manager.id,
                manager_user_id: managerId,
              },
            )}
          type="button"
        >
          Передать
        </Button>
      </Dialog>

      <Dialog open={dialog === "correction"} title="Вернуть на корректировку" onClose={() => setDialog(null)}>
        <label>Комментарий<Textarea maxLength={4000} value={comment} onChange={(event) => setComment(event.target.value)} /></label>
        <details><summary>Добавить альтернативный состав</summary><LineComposer lines={proposal} onChange={setProposal} /></details>
        <Button className="button button--danger" disabled={!comment.trim() || mutation.isPending} onClick={() => act("return-for-correction", { comment, alternative_proposal: proposal.length ? proposal : null })} type="button">Вернуть</Button>
      </Dialog>

      <Dialog open={dialog === "revision"} title="Новая редакция" onClose={() => setDialog(null)}>
        <LineComposer lines={revisionLines} onChange={setRevisionLines} />
        <label>Комментарий<Textarea maxLength={4000} value={comment} onChange={(event) => setComment(event.target.value)} /></label>
        <Button className="button button--accent" disabled={!revisionLines.length || mutation.isPending} onClick={() => act("revisions", { lines: revisionLines, general_comment: comment.trim() || null })} type="button">Отправить редакцию</Button>
      </Dialog>

      <Dialog open={dialog === "discrepancy"} title="Есть расхождения" onClose={() => setDialog(null)}>
        <label>Что отличается<Textarea maxLength={4000} value={comment} onChange={(event) => setComment(event.target.value)} /></label>
        <Button className="button button--danger" disabled={!comment.trim() || mutation.isPending} onClick={() => act("discrepancies", { comment })} type="button">Зафиксировать</Button>
      </Dialog>

      <Dialog open={dialog === "accept"} title="Подтвердить приёмку" onClose={() => setDialog(null)}>
        <p>После подтверждения на склад будет добавлено:</p>
        <ul>{current.current_revision.lines.map((line) => <li key={line.id}>{procurementLineTitle(line)} — {line.quantity} шт.</li>)}</ul>
        {locations.isPending ? (
          <p role="status">Загружаем места приёмки…</p>
        ) : null}
        {locations.isError ? (
          <p role="alert">
            Не удалось загрузить места приёмки.{" "}
            <Button onClick={() => void locations.refetch()} type="button">
              Повторить
            </Button>
          </p>
        ) : null}
        {!locations.isPending
          && !locations.isError
          && activeLocations.length === 0 ? (
            <p>Нет доступных мест приёмки.</p>
          ) : null}
        <label>
          Место приёмки
          <Select
            disabled={
              locations.isPending
              || locations.isError
              || mutation.isPending
            }
            value={locationId}
            onChange={(event) => setLocationId(event.target.value)}
          >
            <option value="">Выберите</option>
            {activeLocations.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.name} · {entry.code}
              </option>
            ))}
          </Select>
        </label>
        <Button
          className="button button--accent"
          disabled={
            !locationId
            || locations.isError
            || mutation.isPending
            || current.current_revision.lines.some(
              (line) => !line.bound_item_id,
            )
          }
          onClick={() =>
            act(
              "acceptance",
              { receiving_location_id: locationId },
            )}
          type="button"
        >
          Подтвердить и оприходовать
        </Button>
      </Dialog>

      <Dialog
        open={bindingLine !== null}
        title="Связать с каталогом"
        onClose={() => setBindingLine(null)}
      >
        <label>
          Поиск
          <Input
            value={bindingSearch}
            onChange={(event) =>
              setBindingSearch(
                event.target.value,
              )}
          />
        </label>

        {bindingSearch.trim().length < 2 ? (
          <p>Введите минимум 2 символа для поиска.</p>
        ) : null}
        {bindingItems.isPending ? (
          <p role="status">Ищем оборудование…</p>
        ) : null}
        {bindingItems.isError ? (
          <p role="alert">
            Не удалось загрузить оборудование.{" "}
            <Button
              onClick={() => void bindingItems.refetch()}
              type="button"
            >
              Повторить
            </Button>
          </p>
        ) : null}
        {bindingSearch.trim().length >= 2
          && !bindingItems.isPending
          && !bindingItems.isError
          && bindingItemOptions.length === 0 ? (
            <p>Оборудование не найдено.</p>
          ) : null}

        <div className="procurement-binding-results">
          {bindingItemOptions.map(
            (item) => (
              <Button
                className="button"
                disabled={mutation.isPending}
                key={item.id}
                onClick={() =>
                  act(
                    "bind-line",
                    {
                      line_id:
                        bindingLine,
                      item_id:
                        item.id,
                    },
                  )}
                type="button"
              >
                {[
                  item.manufacturer?.name,
                  item.name,
                  item.model,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </Button>
            ),
          )}
        </div>

        {bindingItems.hasNextPage ? (
          <Button
            className="button button--load-more"
            disabled={
              bindingItems.isFetchingNextPage
            }
            onClick={() =>
              void bindingItems.fetchNextPage()
            }
            type="button"
          >
            {bindingItems.isFetchingNextPage
              ? "Загружаем…"
              : "Показать ещё"}
          </Button>
        ) : null}
      </Dialog>
    </main>
  );
}
