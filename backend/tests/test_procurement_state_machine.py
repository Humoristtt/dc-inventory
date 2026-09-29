import pytest

from app.modules.procurement.enums import ProcurementStatus
from app.modules.procurement.state_machine import transition_allowed


_ALLOWED = {
    (
        ProcurementStatus.AGREEMENT_PENDING_MANAGER,
        ProcurementStatus.AGREEMENT_REVISION_REQUIRED,
    ),
    (
        ProcurementStatus.AGREEMENT_PENDING_MANAGER,
        ProcurementStatus.PURCHASING,
    ),
    (
        ProcurementStatus.AGREEMENT_REVISION_REQUIRED,
        ProcurementStatus.AGREEMENT_PENDING_MANAGER,
    ),
    (
        ProcurementStatus.PURCHASING,
        ProcurementStatus.AWAITING_ACCEPTANCE,
    ),
    (
        ProcurementStatus.AWAITING_ACCEPTANCE,
        ProcurementStatus.AGREEMENT_REVISION_REQUIRED,
    ),
    (
        ProcurementStatus.AWAITING_ACCEPTANCE,
        ProcurementStatus.COMPLETED,
    ),
}


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (current, target)
        for current in ProcurementStatus
        for target in ProcurementStatus
    ],
)
def test_procurement_transition_matrix_is_exhaustive(
    current: ProcurementStatus,
    target: ProcurementStatus,
) -> None:
    assert transition_allowed(current, target) is (
        (current, target) in _ALLOWED
    )


def test_purchasing_cannot_skip_directly_to_completed() -> None:
    assert not transition_allowed(
        ProcurementStatus.PURCHASING,
        ProcurementStatus.COMPLETED,
    )


def test_completed_request_has_no_outgoing_transition() -> None:
    for target in ProcurementStatus:
        assert not transition_allowed(
            ProcurementStatus.COMPLETED,
            target,
        )
