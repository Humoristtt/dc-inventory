from __future__ import annotations

from app.modules.identity.models import User
from app.modules.identity.policy import Capability, has_capability
from app.modules.procurement.domain import ProcurementRecord
from app.modules.procurement.enums import (
    ACTIVE_PROCUREMENT_STATUSES,
    ProcurementLineType,
    ProcurementStatus,
)


def available_actions(record: ProcurementRecord, actor: User) -> list[str]:
    request = record.request
    actions: list[str] = []
    if (
        has_capability(actor.role, Capability.PROCUREMENT_MANAGE)
        and request.status in ACTIVE_PROCUREMENT_STATUSES
    ):
        if request.assigned_manager_user_id != actor.id:
            actions.append("take_ownership")
        actions.append("transfer_manager")
        if request.status == ProcurementStatus.AGREEMENT_PENDING_MANAGER:
            actions.extend(("manager_accept", "return_for_correction"))
        elif request.status == ProcurementStatus.PURCHASING:
            actions.append("transfer_to_acceptance")
        elif request.status == ProcurementStatus.AWAITING_ACCEPTANCE:
            actions.append("return_for_correction")
    if (
        has_capability(actor.role, Capability.PROCUREMENT_CREATE)
        and actor.id == request.initiator_user_id
        and request.status == ProcurementStatus.AGREEMENT_REVISION_REQUIRED
    ):
        actions.append("submit_revision")
    if has_capability(actor.role, Capability.PROCUREMENT_ACCEPT):
        if request.status != ProcurementStatus.COMPLETED and any(
            line.line_type == ProcurementLineType.PROPOSED_ITEM and line.binding is None
            for line in record.current_revision.lines
        ):
            actions.append("bind_lines")
        if request.status == ProcurementStatus.AWAITING_ACCEPTANCE:
            actions.extend(("report_discrepancy", "complete_acceptance"))
    return actions
