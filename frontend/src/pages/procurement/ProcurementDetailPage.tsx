import { Button } from "../../shared/ui";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  useMemo,
  useRef,
  useState,
} from "react";
import { Navigate, useParams } from "react-router-dom";

import {
  ProcurementDetailDialogs,
} from "../../features/procurement/ProcurementDetailDialogs";
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
  type ProcurementDialogKind,
} from "../../features/procurement/ProcurementActionBar";
import {
  ProcurementCurrentLines,
  ProcurementHistory,
  ProcurementOverview,
  ProcurementRevisions,
} from "../../features/procurement/ProcurementSummarySections";
import {
  procurementInputFromLine,
} from "../../features/procurement/procurementDetailModel";
import { PageHeader } from "../../shared/ui";
import "../../features/procurement/procurement.css";

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

      <ProcurementDetailDialogs
        activeLocations={
          activeLocations
        }
        bindingItemsError={
          bindingItems.isError
        }
        bindingItemsHasNextPage={
          bindingItems.hasNextPage
          ?? false
        }
        bindingItemsLoading={
          bindingItems.isPending
        }
        bindingItemsLoadingNext={
          bindingItems
            .isFetchingNextPage
        }
        bindingItemOptions={
          bindingItemOptions
        }
        bindingLine={bindingLine}
        bindingSearch={
          bindingSearch
        }
        comment={comment}
        current={current}
        dialog={dialog}
        locationId={locationId}
        locationsError={
          locations.isError
        }
        locationsLoading={
          locations.isPending
        }
        managerId={managerId}
        managerOptions={
          managerOptions
        }
        managerSearch={
          managerSearch
        }
        managersError={
          managers.isError
        }
        managersHasNextPage={
          managers.hasNextPage
          ?? false
        }
        managersLoading={
          managers.isPending
        }
        managersLoadingNext={
          managers
            .isFetchingNextPage
        }
        mutationPending={
          mutation.isPending
        }
        onAction={act}
        onBindingSearchChange={
          setBindingSearch
        }
        onCloseDialog={() =>
          setDialog(null)
        }
        onCommentChange={
          setComment
        }
        onFetchMoreBindingItems={
          () =>
            void bindingItems
              .fetchNextPage()
        }
        onFetchMoreManagers={
          () =>
            void managers
              .fetchNextPage()
        }
        onLocationChange={
          setLocationId
        }
        onManagerChange={
          setManagerId
        }
        onManagerSearchChange={
          (value) => {
            setManagerSearch(value);
            setManagerId("");
          }
        }
        onProposalChange={
          setProposal
        }
        onRetryBindingItems={
          () =>
            void bindingItems
              .refetch()
        }
        onRetryLocations={
          () =>
            void locations.refetch()
        }
        onRetryManagers={
          () =>
            void managers.refetch()
        }
        onRevisionLinesChange={
          setRevisionLines
        }
        onSetBindingLine={
          setBindingLine
        }
        proposal={proposal}
        revisionLines={
          revisionLines
        }
      />
    </main>
  );
}
