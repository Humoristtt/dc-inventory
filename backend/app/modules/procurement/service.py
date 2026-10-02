"""Public procurement service façade.

Mutation implementations are split by responsibility:
- workflow.py: request lifecycle and assignment;
- acceptance.py: catalog binding and warehouse acceptance;
- queries.py: read paths;
- domain.py: errors and records.
"""

from app.modules.procurement.acceptance import (
    bind_line,
    complete_acceptance,
    create_and_bind_line,
    report_discrepancy,
)
from app.modules.procurement.actions import available_actions
from app.modules.procurement.domain import (
    ProcurementConflictError,
    ProcurementError,
    ProcurementForbiddenError,
    ProcurementNotFoundError,
    ProcurementPage,
    ProcurementRecord,
    ProcurementServiceUnavailableError,
    ProcurementSummaryRecord,
    ProcurementValidationError,
)
from app.modules.procurement.queries import (
    get_request_record,
    list_managers,
    list_requests,
)
from app.modules.procurement.workflow import (
    create_request,
    manager_accept,
    return_for_correction,
    submit_revision,
    take_ownership,
    transfer_manager,
    transfer_to_acceptance,
)

__all__ = (
    "ProcurementConflictError",
    "ProcurementError",
    "ProcurementForbiddenError",
    "ProcurementNotFoundError",
    "ProcurementPage",
    "ProcurementRecord",
    "ProcurementServiceUnavailableError",
    "ProcurementSummaryRecord",
    "ProcurementValidationError",
    "available_actions",
    "bind_line",
    "complete_acceptance",
    "create_and_bind_line",
    "create_request",
    "get_request_record",
    "list_managers",
    "list_requests",
    "manager_accept",
    "report_discrepancy",
    "return_for_correction",
    "submit_revision",
    "take_ownership",
    "transfer_manager",
    "transfer_to_acceptance",
)
