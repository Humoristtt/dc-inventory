import {
  useRef,
} from "react";
import {
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import {
  useNavigate,
} from "react-router-dom";

import {
  createCatalogItem,
  createCatalogManufacturer,
  patchCatalogItem,
  type ItemWritePayload,
} from "../../shared/api/catalog";
import {
  createAndBindProcurementLine,
  type ProcurementRequest,
} from "../../shared/api/procurement";

export function useItemFormMutations({
  itemId,
  manufacturerName,
  procurement,
  procurementLineId,
  procurementRequestId,
  onManufacturerCreated,
}: {
  itemId: string | undefined;
  manufacturerName: string;
  procurement:
    | ProcurementRequest
    | undefined;
  procurementLineId:
    | string
    | null;
  procurementRequestId:
    | string
    | null;
  onManufacturerCreated: (
    manufacturer: {
      id: string;
      name: string;
    },
  ) => void;
}) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const procurementIntentRef =
    useRef<{
      fingerprint: string;
      clientRequestId: string;
    } | null>(null);
  const mutationInFlightRef =
    useRef(false);

  const makerMutation = useMutation({
    mutationFn: () =>
      createCatalogManufacturer(
        manufacturerName,
      ),
    onSuccess: (maker) => {
      onManufacturerCreated(
        maker,
      );

      void client.invalidateQueries({
        queryKey: [
          "catalog",
          "manufacturer-suggestions",
        ],
      });
    },
  });

  const mutation = useMutation({
    mutationFn:
      async (
        payload: ItemWritePayload,
      ) => {
        if (itemId) {
          const {
            category_key:
              _categoryKey,
            ...patch
          } = payload;

          return {
            kind: "item" as const,
            saved:
              await patchCatalogItem(
                itemId,
                patch,
              ),
          };
        }

        if (
          procurement
          && procurementLineId
          && procurementRequestId
        ) {
          const fingerprint =
            JSON.stringify({
              requestId:
                procurement.id,
              stateVersion:
                procurement
                  .state_version,
              revisionId:
                procurement
                  .current_revision_id,
              lineId:
                procurementLineId,
              item: payload,
            });

          let intent =
            procurementIntentRef.current;

          if (
            intent === null
            || intent.fingerprint
              !== fingerprint
          ) {
            intent = {
              fingerprint,
              clientRequestId:
                crypto.randomUUID(),
            };
            procurementIntentRef
              .current = intent;
          }

          return {
            kind:
              "procurement"
              as const,
            saved:
              await createAndBindProcurementLine(
                procurement,
                procurementLineId,
                payload,
                intent
                  .clientRequestId,
              ),
          };
        }

        return {
          kind: "item" as const,
          saved:
            await createCatalogItem(
              payload,
            ),
        };
      },
    onSuccess: ({
      kind,
      saved,
    }) => {
      if (
        kind === "procurement"
      ) {
        procurementIntentRef
          .current = null;

        client.setQueryData(
          [
            "procurement",
            "request",
            saved.id,
          ],
          saved,
        );

        void client
          .invalidateQueries({
            queryKey: [
              "catalog",
            ],
          });

        navigate(
          `/procurement/${saved.id}`,
          { replace: true },
        );
        return;
      }

      client.setQueryData(
        [
          "catalog",
          "item",
          saved.id,
        ],
        saved,
      );

      for (const key of [
        ["catalog", "items"],
        ["catalog", "facets"],
        [
          "catalog",
          "form-model-suggestions",
        ],
        [
          "catalog",
          "form-name-suggestions",
        ],
        [
          "catalog",
          "form-attribute-suggestions",
        ],
      ] as const) {
        void client
          .invalidateQueries({
            queryKey: key,
          });
      }

      navigate(
        `/catalog/items/${saved.id}`,
        { replace: true },
      );
    },
    onSettled: () => {
      mutationInFlightRef
        .current = false;
    },
  });

  const save = (
    payload: ItemWritePayload,
  ): boolean => {
    if (
      mutation.isPending
      || mutationInFlightRef.current
    ) {
      return false;
    }

    mutationInFlightRef.current =
      true;
    mutation.mutate(payload);
    return true;
  };

  return {
    makerMutation,
    mutation,
    save,
  };
}
