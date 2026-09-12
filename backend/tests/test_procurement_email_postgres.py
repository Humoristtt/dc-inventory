import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.procurement.email import (
    ClaimedEmail,
    claim_email_batch,
    finalize_email,
)
from app.modules.procurement.enums import ProcurementStatus
from app.modules.procurement.models import EmailOutbox
from tests.test_procurement_postgres import seed_procurement

pytestmark = pytest.mark.asyncio


async def seed_email(
    db: AsyncSession,
    *,
    attempts: int = 0,
    claimed_at: datetime | None = None,
    claim_token: uuid.UUID | None = None,
    available_at: datetime | None = None,
) -> EmailOutbox:
    (
        _initiator,
        manager,
        senior,
        _item_id,
        location,
        record,
    ) = await seed_procurement(db)

    from app.modules.procurement.schemas import ProcurementAcceptanceCreate
    from app.modules.procurement.service import complete_acceptance
    from tests.test_procurement_postgres import move_to_acceptance, settings

    record = await move_to_acceptance(
        db,
        record,
        manager_id=manager.id,
    )

    record = await complete_acceptance(
        db,
        record.request.id,
        ProcurementAcceptanceCreate(
            expected_state_version=record.request.state_version,
            expected_revision_id=record.request.current_revision_id,
            client_request_id=uuid.uuid4().hex,
            receiving_location_id=location.id,
        ),
        actor_user_id=senior.id,
        settings=settings(),
    )

    assert record.request.status == ProcurementStatus.COMPLETED

    row = EmailOutbox(
        id=uuid.uuid4(),
        request_id=record.request.id,
        to_addresses=["receiver@example.test"],
        cc_addresses=[],
        subject="Synthetic email",
        text_body="Synthetic email body",
        html_body="<p>Synthetic email body</p>",
        dedupe_key=uuid.uuid4().hex,
        attempts=attempts,
        available_at=available_at or datetime.now(UTC),
        claimed_at=claimed_at,
        claim_token=claim_token,
    )
    db.add(row)
    await db.flush()
    return row


async def test_stale_final_attempt_can_be_reclaimed_without_increment(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    now = datetime.now(UTC)
    old_token = uuid.uuid4()

    row = await seed_email(
        db,
        attempts=3,
        claimed_at=now - timedelta(minutes=10),
        claim_token=old_token,
        available_at=now - timedelta(seconds=1),
    )

    claims = await claim_email_batch(
        db,
        batch_size=1,
        claim_ttl_seconds=60,
        max_attempts=3,
        now=now,
    )

    assert len(claims) == 1
    claim = claims[0]

    assert claim.id == row.id
    assert claim.attempts == 3
    assert claim.claim_token != old_token

    refreshed = await db.get(EmailOutbox, row.id)
    assert refreshed is not None
    assert refreshed.attempts == 3
    assert refreshed.claim_token == claim.claim_token


async def test_failed_final_attempt_becomes_dead(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    row = await seed_email(
        db,
        attempts=2,
    )

    claims = await claim_email_batch(
        db,
        batch_size=1,
        claim_ttl_seconds=60,
        max_attempts=3,
    )

    assert len(claims) == 1
    claim = claims[0]
    assert claim.attempts == 3

    finalized = await finalize_email(
        db,
        claim,
        error="SyntheticDeliveryError",
        max_attempts=3,
    )

    assert finalized is True

    refreshed = await db.get(EmailOutbox, row.id)
    assert refreshed is not None
    assert refreshed.status == "DEAD"
    assert refreshed.claimed_at is None
    assert refreshed.claim_token is None
    assert refreshed.last_error == "SyntheticDeliveryError"


async def test_successful_email_becomes_sent(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    row = await seed_email(db)

    claims = await claim_email_batch(
        db,
        batch_size=1,
        claim_ttl_seconds=60,
        max_attempts=3,
    )

    assert len(claims) == 1
    claim = claims[0]

    finalized = await finalize_email(
        db,
        claim,
        error=None,
        max_attempts=3,
    )

    assert finalized is True

    refreshed = await db.get(EmailOutbox, row.id)
    assert refreshed is not None
    assert refreshed.status == "SENT"
    assert refreshed.sent_at is not None
    assert refreshed.last_error is None


async def test_stale_claim_token_cannot_finalize_new_claim(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db
    row = await seed_email(db)

    claims = await claim_email_batch(
        db,
        batch_size=1,
        claim_ttl_seconds=60,
        max_attempts=3,
    )

    assert len(claims) == 1
    claim = claims[0]

    stale_claim = ClaimedEmail(
        id=claim.id,
        claim_token=uuid.uuid4(),
        to=claim.to,
        cc=claim.cc,
        subject=claim.subject,
        text_body=claim.text_body,
        html_body=claim.html_body,
        attempts=claim.attempts,
    )

    finalized = await finalize_email(
        db,
        stale_claim,
        error=None,
        max_attempts=3,
    )

    assert finalized is False

    refreshed = await db.get(EmailOutbox, row.id)
    assert refreshed is not None
    assert refreshed.status == "PENDING"
    assert refreshed.claim_token == claim.claim_token


async def test_claim_batch_size_one_claims_only_one_row(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    first = await seed_email(db)
    second = await seed_email(db)

    claims = await claim_email_batch(
        db,
        batch_size=1,
        claim_ttl_seconds=60,
        max_attempts=3,
    )

    assert len(claims) == 1

    rows = (
        await db.scalars(
            select(EmailOutbox)
            .where(EmailOutbox.id.in_([first.id, second.id]))
            .order_by(EmailOutbox.id)
        )
    ).all()

    assert sum(row.claimed_at is not None for row in rows) == 1


async def test_worker_claims_exactly_one_email_at_a_time(
    migration_database: str,
) -> None:
    from sqlalchemy import func
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.core.config import Settings
    from app.modules.procurement.email import run_email_worker_once
    from tests.migration_helpers import alembic

    alembic(migration_database, "upgrade", "head")
    engine = create_async_engine(migration_database)

    async with (
        AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db,
        db.begin(),
    ):
        first = await seed_email(db)
        second = await seed_email(db)
        email_ids = {first.id, second.id}

    class InspectingClient:
        def __init__(self) -> None:
            self.claimed_counts: list[int] = []
            self.sent_ids: list[uuid.UUID] = []

        async def send(self, claim: ClaimedEmail) -> None:
            async with AsyncSession(
                engine,
                expire_on_commit=False,
            ) as db:
                claimed_count = await db.scalar(
                    select(func.count(EmailOutbox.id)).where(
                        EmailOutbox.id.in_(email_ids),
                        EmailOutbox.status == "PENDING",
                        EmailOutbox.claimed_at.is_not(None),
                    )
                )
            self.claimed_counts.append(claimed_count or 0)
            self.sent_ids.append(claim.id)

    client = InspectingClient()

    processed = await run_email_worker_once(
        engine,
        cast(Any, client),
        Settings(
            app_env="test",
            email_worker_batch_size=2,
            email_worker_max_attempts=3,
        ),
    )

    assert processed == 2
    assert client.claimed_counts == [1, 1]
    assert set(client.sent_ids) == email_ids

    async with AsyncSession(
        engine,
        expire_on_commit=False,
    ) as db:
        rows = (await db.scalars(select(EmailOutbox).where(EmailOutbox.id.in_(email_ids)))).all()

        assert len(rows) == 2
        assert all(row.status == "SENT" for row in rows)
        assert all(row.claimed_at is None for row in rows)
        assert all(row.claim_token is None for row in rows)

    await engine.dispose()


async def test_worker_delivery_failure_reaches_dead_at_max_attempts(
    migration_database: str,
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.core.config import Settings
    from app.modules.procurement.email import run_email_worker_once
    from tests.migration_helpers import alembic

    alembic(migration_database, "upgrade", "head")
    engine = create_async_engine(migration_database)

    async with (
        AsyncSession(
            engine,
            expire_on_commit=False,
        ) as db,
        db.begin(),
    ):
        row = await seed_email(db)
        email_id = row.id

    class FailingClient:
        async def send(self, claim: ClaimedEmail) -> None:
            raise RuntimeError("synthetic Graph failure")

    processed = await run_email_worker_once(
        engine,
        cast(Any, FailingClient()),
        Settings(
            app_env="test",
            email_worker_batch_size=1,
            email_worker_max_attempts=1,
        ),
    )

    assert processed == 1

    async with AsyncSession(
        engine,
        expire_on_commit=False,
    ) as db:
        stored = await db.get(EmailOutbox, email_id)

        assert stored is not None
        assert stored.status == "DEAD"
        assert stored.attempts == 1
        assert stored.claimed_at is None
        assert stored.claim_token is None
        assert stored.last_error == "RuntimeError"

    await engine.dispose()
