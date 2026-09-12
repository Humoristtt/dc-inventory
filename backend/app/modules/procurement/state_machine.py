from app.modules.procurement.enums import ProcurementStatus

ALLOWED_TRANSITIONS: dict[ProcurementStatus, frozenset[ProcurementStatus]] = {
    ProcurementStatus.AGREEMENT_PENDING_MANAGER: frozenset(
        {
            ProcurementStatus.AGREEMENT_REVISION_REQUIRED,
            ProcurementStatus.PURCHASING,
        }
    ),
    ProcurementStatus.AGREEMENT_REVISION_REQUIRED: frozenset(
        {ProcurementStatus.AGREEMENT_PENDING_MANAGER}
    ),
    ProcurementStatus.PURCHASING: frozenset({ProcurementStatus.AWAITING_ACCEPTANCE}),
    ProcurementStatus.AWAITING_ACCEPTANCE: frozenset(
        {
            ProcurementStatus.AGREEMENT_REVISION_REQUIRED,
            ProcurementStatus.COMPLETED,
        }
    ),
    ProcurementStatus.COMPLETED: frozenset(),
}


def transition_allowed(
    current: ProcurementStatus,
    target: ProcurementStatus,
) -> bool:
    return target in ALLOWED_TRANSITIONS[current]
