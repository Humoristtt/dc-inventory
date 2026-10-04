from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.idempotency import normalize_idempotency_key
from app.modules.identity.models import TelegramIdentity
from app.modules.procurement.models import (
    ProcurementEvent,
    ProcurementRequest,
    ProcurementRevision,
)


class ProcurementError(RuntimeError):
    code = "procurement_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class ProcurementValidationError(ProcurementError):
    code = "procurement_validation_error"


class ProcurementNotFoundError(ProcurementError):
    code = "procurement_not_found"


class ProcurementConflictError(ProcurementError):
    code = "procurement_conflict"


class ProcurementForbiddenError(ProcurementError):
    code = "procurement_forbidden"


class ProcurementServiceUnavailableError(ProcurementError):
    code = "procurement_service_unavailable"


MAX_AGGREGATED_ITEM_QUANTITY = 2**53 - 1


@dataclass(frozen=True, slots=True)
class ProcurementRecord:
    request: ProcurementRequest
    revisions: list[ProcurementRevision]
    events: list[ProcurementEvent]
    display_names: dict[uuid.UUID, str]

    @property
    def current_revision(self) -> ProcurementRevision:
        for revision in self.revisions:
            if revision.id == self.request.current_revision_id:
                return revision
        raise RuntimeError("procurement current revision was not loaded")


@dataclass(frozen=True, slots=True)
class ProcurementSummaryRecord:
    request: ProcurementRequest
    current_revision: ProcurementRevision
    display_names: dict[uuid.UUID, str]


@dataclass(frozen=True, slots=True)
class ProcurementPage:
    items: list[ProcurementSummaryRecord]
    total: int


def _normalize_client_request_id(value: str) -> str:
    normalized = normalize_idempotency_key(value)
    if not normalized:
        raise ProcurementValidationError(
            "client_request_id must not be blank", code="client_request_id_required"
        )
    if len(normalized) > 128:
        raise ProcurementValidationError(
            "client_request_id exceeds 128 characters", code="client_request_id_too_long"
        )
    return normalized


def _normalize_comment(value: str | None, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ProcurementValidationError("comment is required", code="comment_required")
        return None
    normalized = value.strip()
    if not normalized:
        if required:
            raise ProcurementValidationError("comment is required", code="comment_required")
        return None
    return normalized


def _display_name(identity: TelegramIdentity | None, user_id: uuid.UUID) -> str:
    if identity is None:
        return str(user_id)
    name = " ".join(part for part in (identity.first_name, identity.last_name) if part).strip()
    if identity.username:
        return f"{name} (@{identity.username})" if name else f"@{identity.username}"
    return name or str(user_id)
