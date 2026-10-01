import {
  ProcurementAcceptanceDialog,
} from "./ProcurementAcceptanceDialog";
import {
  ProcurementBindingDialog,
} from "./ProcurementBindingDialog";
import {
  ProcurementEditDialogs,
} from "./ProcurementEditDialogs";
import {
  ProcurementManagerDialog,
} from "./ProcurementManagerDialog";
import type {
  CatalogItemListEntry,
} from "../../shared/api/catalog";
import type {
  StorageLocation,
} from "../../shared/api/inventory";
import type {
  ProcurementLineInput,
  ProcurementRequest,
  UserSummary,
} from "../../shared/api/procurement";
import type {
  ProcurementDialogKind,
} from "./ProcurementActionBar";
import type {
  ProcurementAction,
} from "./procurementDetailDialogTypes";

export function ProcurementDetailDialogs(props: {
  activeLocations:
    readonly StorageLocation[];
  bindingItemsError: boolean;
  bindingItemsHasNextPage: boolean;
  bindingItemsLoading: boolean;
  bindingItemsLoadingNext: boolean;
  bindingItemOptions:
    readonly CatalogItemListEntry[];
  bindingLine:
    | string
    | null;
  bindingSearch: string;
  comment: string;
  current: ProcurementRequest;
  dialog:
    | ProcurementDialogKind
    | null;
  locationId: string;
  locationsError: boolean;
  locationsLoading: boolean;
  managerId: string;
  managerOptions:
    readonly UserSummary[];
  managerSearch: string;
  managersError: boolean;
  managersHasNextPage: boolean;
  managersLoading: boolean;
  managersLoadingNext: boolean;
  mutationPending: boolean;
  proposal:
    ProcurementLineInput[];
  revisionLines:
    ProcurementLineInput[];
  onAction: ProcurementAction;
  onBindingSearchChange:
    (value: string) => void;
  onCloseDialog: () => void;
  onCommentChange:
    (value: string) => void;
  onFetchMoreBindingItems:
    () => void;
  onFetchMoreManagers:
    () => void;
  onLocationChange:
    (value: string) => void;
  onManagerChange:
    (value: string) => void;
  onManagerSearchChange:
    (value: string) => void;
  onProposalChange:
    (lines:
      ProcurementLineInput[],
    ) => void;
  onRetryBindingItems:
    () => void;
  onRetryLocations:
    () => void;
  onRetryManagers:
    () => void;
  onRevisionLinesChange:
    (lines:
      ProcurementLineInput[],
    ) => void;
  onSetBindingLine:
    (
      lineId:
        | string
        | null,
    ) => void;
}) {
  return (
    <>
      <ProcurementManagerDialog
        current={props.current}
        managerId={props.managerId}
        managerOptions={
          props.managerOptions
        }
        managerSearch={
          props.managerSearch
        }
        managersError={
          props.managersError
        }
        managersHasNextPage={
          props.managersHasNextPage
        }
        managersLoading={
          props.managersLoading
        }
        managersLoadingNext={
          props.managersLoadingNext
        }
        mutationPending={
          props.mutationPending
        }
        onAction={props.onAction}
        onClose={
          props.onCloseDialog
        }
        onFetchMore={
          props.onFetchMoreManagers
        }
        onManagerChange={
          props.onManagerChange
        }
        onManagerSearchChange={
          props.onManagerSearchChange
        }
        onRetry={
          props.onRetryManagers
        }
        open={
          props.dialog
          === "transfer"
        }
      />

      <ProcurementEditDialogs
        comment={props.comment}
        dialog={props.dialog}
        mutationPending={
          props.mutationPending
        }
        onAction={props.onAction}
        onClose={
          props.onCloseDialog
        }
        onCommentChange={
          props.onCommentChange
        }
        onProposalChange={
          props.onProposalChange
        }
        onRevisionLinesChange={
          props.onRevisionLinesChange
        }
        proposal={props.proposal}
        revisionLines={
          props.revisionLines
        }
      />

      <ProcurementAcceptanceDialog
        activeLocations={
          props.activeLocations
        }
        current={props.current}
        locationId={
          props.locationId
        }
        locationsError={
          props.locationsError
        }
        locationsLoading={
          props.locationsLoading
        }
        mutationPending={
          props.mutationPending
        }
        onAction={props.onAction}
        onClose={
          props.onCloseDialog
        }
        onLocationChange={
          props.onLocationChange
        }
        onRetryLocations={
          props.onRetryLocations
        }
        open={
          props.dialog === "accept"
        }
      />

      <ProcurementBindingDialog
        bindingItemsError={
          props.bindingItemsError
        }
        bindingItemsHasNextPage={
          props.bindingItemsHasNextPage
        }
        bindingItemsLoading={
          props.bindingItemsLoading
        }
        bindingItemsLoadingNext={
          props.bindingItemsLoadingNext
        }
        bindingItemOptions={
          props.bindingItemOptions
        }
        bindingLine={
          props.bindingLine
        }
        bindingSearch={
          props.bindingSearch
        }
        mutationPending={
          props.mutationPending
        }
        onAction={props.onAction}
        onBindingSearchChange={
          props.onBindingSearchChange
        }
        onClose={() =>
          props.onSetBindingLine(
            null,
          )
        }
        onFetchMore={
          props.onFetchMoreBindingItems
        }
        onRetry={
          props.onRetryBindingItems
        }
      />
    </>
  );
}
