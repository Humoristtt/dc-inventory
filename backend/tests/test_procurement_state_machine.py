from app.modules.procurement.enums import ProcurementStatus
from app.modules.procurement.state_machine import transition_allowed


def test_acceptance_may_return_to_correction() -> None:
    assert transition_allowed(
        ProcurementStatus.AWAITING_ACCEPTANCE,
        ProcurementStatus.AGREEMENT_REVISION_REQUIRED,
    )


def test_acceptance_may_complete() -> None:
    assert transition_allowed(
        ProcurementStatus.AWAITING_ACCEPTANCE,
        ProcurementStatus.COMPLETED,
    )


def test_completed_request_has_no_outgoing_transition() -> None:
    for target in ProcurementStatus:
        assert not transition_allowed(
            ProcurementStatus.COMPLETED,
            target,
        )
