from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.idempotency import advisory_lock_key
from app.modules.inventory.domain import (
    InventoryConflictError,
    MovementRecord,
    MovementResult,
)
from app.modules.inventory.enums import MovementType
from app.modules.inventory.models import Movement


def _custody_delta(
    movement_type: MovementType,
    original: MovementRecord | None,
) -> int:
    if movement_type == MovementType.ISSUE:
        return 1
    if movement_type == MovementType.RETURN:
        return -1
    if movement_type != MovementType.REVERSAL or original is None:
        return 0
    if original.movement.movement_type == MovementType.ISSUE:
        return -1
    if original.movement.movement_type == MovementType.RETURN:
        return 1
    return 0


async def _lock_idempotency_key(
    db: AsyncSession,
    actor_user_id: uuid.UUID,
    client_request_id: str,
) -> None:
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                advisory_lock_key(
                    "warehouse-idempotency",
                    actor_user_id,
                    client_request_id,
                )
            )
        )
    )


async def _lock_original_movement_context(
    db: AsyncSession,
    movement_id: uuid.UUID,
) -> None:
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                advisory_lock_key(
                    "warehouse-original-movement",
                    movement_id,
                )
            )
        )
    )


async def _existing_idempotent_result(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    client_request_id: str,
    request_fingerprint: str,
) -> MovementResult | None:
    movement = await db.scalar(
        select(Movement)
        .where(
            Movement.actor_user_id == actor_user_id,
            Movement.client_request_id == client_request_id,
        )
        .options(selectinload(Movement.lines))
    )
    if movement is None:
        return None
    if movement.request_fingerprint != request_fingerprint:
        raise InventoryConflictError(
            "idempotency key was already used with a different payload",
            code="idempotency_payload_conflict",
        )
    return MovementResult(
        record=MovementRecord(movement=movement, lines=list(movement.lines)),
        replayed=True,
    )
