from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from app.modules.procurement.enums import (
    ProcurementEventType,
    ProcurementLineType,
    ProcurementStatus,
)

type ProcurementScalar = str | int | Decimal | bool


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExistingItemLineCreate(StrictRequestModel):
    line_type: Literal[ProcurementLineType.EXISTING_ITEM]
    item_id: UUID
    quantity: StrictInt = Field(gt=0, le=2**53 - 1)


class ProposedItemLineCreate(StrictRequestModel):
    line_type: Literal[ProcurementLineType.PROPOSED_ITEM]
    category_key: str = Field(min_length=1, max_length=64)
    manufacturer_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    model: str | None = Field(default=None, max_length=255)
    attributes: dict[str, ProcurementScalar] = Field(default_factory=dict)
    quantity: StrictInt = Field(gt=0, le=2**53 - 1)


ProcurementLineCreate = Annotated[
    ExistingItemLineCreate | ProposedItemLineCreate,
    Field(discriminator="line_type"),
]


class ProcurementRequestCreate(StrictRequestModel):
    assigned_manager_user_id: UUID
    general_comment: str | None = Field(default=None, max_length=4000)
    client_request_id: str = Field(min_length=1, max_length=128)
    lines: list[ProcurementLineCreate] = Field(min_length=1, max_length=500)


class ExpectedStateMutation(StrictRequestModel):
    expected_state_version: StrictInt = Field(ge=1)
    expected_revision_id: UUID
    client_request_id: str = Field(min_length=1, max_length=128)


class CorrectionRequest(ExpectedStateMutation):
    comment: str = Field(min_length=1, max_length=4000)
    alternative_proposal: list[ProcurementLineCreate] | None = Field(
        default=None, min_length=1, max_length=500
    )


class RevisionCreate(ExpectedStateMutation):
    general_comment: str | None = Field(default=None, max_length=4000)
    lines: list[ProcurementLineCreate] = Field(min_length=1, max_length=500)


class AssignmentMutation(ExpectedStateMutation):
    expected_assigned_manager_user_id: UUID


class ManagerTransfer(AssignmentMutation):
    manager_user_id: UUID


class LineBindingCreate(ExpectedStateMutation):
    item_id: UUID
    line_id: UUID


class DiscrepancyCreate(ExpectedStateMutation):
    comment: str = Field(min_length=1, max_length=4000)


class ProcurementAcceptanceCreate(ExpectedStateMutation):
    receiving_location_id: UUID


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class ProcurementEmailCreate(StrictRequestModel):
    to: list[str] = Field(min_length=1, max_length=50)
    cc: list[str] = Field(default_factory=list, max_length=50)
    client_request_id: str = Field(min_length=1, max_length=128)

    @field_validator("to", "cc")
    @classmethod
    def validate_addresses(cls, addresses: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for address in addresses:
            value = address.strip().casefold()
            if len(value) > 254 or EMAIL_PATTERN.fullmatch(value) is None:
                raise ValueError("invalid email address")
            if value not in seen:
                normalized.append(value)
                seen.add(value)
        return normalized


class UserSummaryOut(BaseModel):
    id: UUID
    display_name: str


class ProcurementManagerPageOut(BaseModel):
    items: list[UserSummaryOut]
    total: int
    limit: int
    offset: int


class ProcurementLineOut(BaseModel):
    id: UUID
    line_no: int
    line_type: ProcurementLineType
    catalog_item_id: UUID | None
    bound_item_id: UUID | None
    display_snapshot: dict[str, object]
    quantity: int


class ProcurementRevisionOut(BaseModel):
    id: UUID
    revision_number: int
    submitted_by: UserSummaryOut
    general_comment: str | None
    created_at: datetime
    lines: list[ProcurementLineOut]


class ProcurementEventOut(BaseModel):
    id: UUID
    event_type: ProcurementEventType
    actor: UserSummaryOut
    from_status: ProcurementStatus | None
    to_status: ProcurementStatus | None
    revision_id: UUID | None
    comment: str | None
    metadata: dict[str, object] | None
    occurred_at: datetime


class ProcurementRequestSummaryOut(BaseModel):
    id: UUID
    request_number: str
    status: ProcurementStatus
    status_label: str
    initiator: UserSummaryOut
    assigned_manager: UserSummaryOut
    current_revision_id: UUID
    revision_number: int
    line_count: int
    state_version: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ProcurementRequestPageOut(BaseModel):
    items: list[ProcurementRequestSummaryOut]
    total: int
    limit: int
    offset: int


class ProcurementRequestOut(ProcurementRequestSummaryOut):
    current_revision: ProcurementRevisionOut
    revisions: list[ProcurementRevisionOut]
    events: list[ProcurementEventOut]
    final_movement_id: UUID | None
    available_actions: list[str]


class ProcurementEmailOut(BaseModel):
    id: UUID
    status: Literal["PENDING", "SENT", "DEAD"]
    dedupe_key: str
