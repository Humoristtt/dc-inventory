import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.catalog.models import Item, Manufacturer
from app.modules.catalog.schemas import ItemCreate
from app.modules.catalog.service import (
    CatalogValidationError,
    create_item,
    set_item_archived,
    validate_item_create_payload,
)
from app.modules.identity.enums import UserRole
from app.modules.procurement.enums import (
    ProcurementLineType,
)
from app.modules.procurement.schemas import (
    ExistingItemLineCreate,
    ProcurementRequestCreate,
    ProposedItemLineCreate,
)
from app.modules.procurement.service import (
    ProcurementConflictError,
    _prepare_lines,
    create_request,
    list_requests,
)
from tests.warehouse_helpers import actor, cable_payload

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def captured_statements(
    db: AsyncSession,
) -> AsyncIterator[list[str]]:
    connection = await db.connection()
    target = connection.sync_connection
    statements: list[str] = []

    def before_cursor_execute(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        normalized = " ".join(statement.split())

        if normalized.upper().startswith(("SELECT ", "WITH ")):
            statements.append(normalized)

    event.listen(
        target,
        "before_cursor_execute",
        before_cursor_execute,
    )

    try:
        yield statements
    finally:
        event.remove(
            target,
            "before_cursor_execute",
            before_cursor_execute,
        )


async def test_procurement_list_summary_does_not_load_full_history(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    initiator, _ = await actor(
        db,
        UserRole.ADMIN,
    )

    manager, _ = await actor(
        db,
        UserRole.MANAGER,
    )

    initiator_id = initiator.id
    manager_id = manager.id

    item_id = await create_item(
        db,
        cable_payload(),
    )

    await create_request(
        db,
        ProcurementRequestCreate(
            assigned_manager_user_id=manager_id,
            general_comment="CP06 summary query",
            client_request_id=uuid.uuid4().hex,
            lines=[
                ExistingItemLineCreate(
                    line_type=(ProcurementLineType.EXISTING_ITEM),
                    item_id=item_id,
                    quantity=1,
                )
            ],
        ),
        actor_user_id=initiator_id,
        settings=Settings(app_env="test"),
    )

    await db.flush()
    db.expire_all()

    async with captured_statements(db) as statements:
        page = await list_requests(
            db,
            actor_user_id=manager_id,
            view="active",
            limit=30,
            offset=0,
        )

    assert page.total >= 1
    assert page.items

    lowered = [statement.lower() for statement in statements]

    forbidden_tables = (
        "procurement_events",
        "procurement_revision_lines",
        "procurement_line_catalog_bindings",
    )

    history_statements = [
        statement for statement in lowered if any(table in statement for table in forbidden_tables)
    ]

    assert not history_statements, (
        "CP06 summary list must not load full "
        "Procurement history; "
        f"history_sql={history_statements}"
    )

    assert len(statements) <= 4, (
        "CP06 Procurement summary query count "
        "must remain bounded; "
        f"queries={len(statements)} "
        f"sql={lowered}"
    )


def proposed_line() -> ProposedItemLineCreate:
    draft = cable_payload()

    return ProposedItemLineCreate(
        line_type=ProcurementLineType.PROPOSED_ITEM,
        category_key=draft.category_key,
        manufacturer_id=draft.manufacturer_id,
        name=draft.name,
        model=draft.model,
        attributes=draft.attributes,
        quantity=1,
    )


async def prepare_line_query_counts(
    db: AsyncSession,
    *,
    item_id: uuid.UUID,
    mode: str,
) -> dict[int, int]:
    counts: dict[int, int] = {}

    if mode == "existing":
        template = ExistingItemLineCreate(
            line_type=ProcurementLineType.EXISTING_ITEM,
            item_id=item_id,
            quantity=1,
        )
    else:
        template = proposed_line()

    for size in (
        1,
        100,
        500,
    ):
        db.expire_all()

        async with captured_statements(db) as statements:
            rows = await _prepare_lines(
                db,
                [template for _ in range(size)],
                uuid.uuid4(),
            )

        assert len(rows) == size

        counts[size] = len(statements)

    return counts


@pytest.mark.parametrize(
    "mode",
    [
        "existing",
        "proposed",
    ],
)
async def test_prepare_lines_query_count_is_bounded_by_metadata_not_line_count(
    warehouse_db: AsyncSession,
    mode: str,
) -> None:
    db = warehouse_db

    item_id = await create_item(
        db,
        cable_payload(),
    )

    counts = await prepare_line_query_counts(
        db,
        item_id=item_id,
        mode=mode,
    )

    baseline = counts[1]
    allowed = baseline + 6

    assert counts[100] <= allowed, (
        "CP06 prepare-lines query count must stay "
        "bounded as line count grows; "
        f"mode={mode} counts={counts} "
        f"allowed={allowed}"
    )

    assert counts[500] <= allowed, (
        "CP06 prepare-lines query count must stay "
        "bounded as line count grows; "
        f"mode={mode} counts={counts} "
        f"allowed={allowed}"
    )


async def test_prepare_lines_500_distinct_existing_items(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    item_ids: list[uuid.UUID] = []
    expected_colors: dict[uuid.UUID, str] = {}

    for _ in range(500):
        payload = cable_payload()
        item_id = await create_item(db, payload)

        item_ids.append(item_id)
        expected_colors[item_id] = str(payload.attributes["color"])

    assert len(set(item_ids)) == 500

    signatures = dict(
        (
            await db.execute(
                select(
                    Item.id,
                    Item.identity_signature,
                ).where(Item.id.in_(item_ids))
            )
        ).all()
    )

    assert len(signatures) == 500

    counts: dict[int, int] = {}

    for size in (1, 100, 500):
        selected = list(reversed(item_ids[:size]))

        payloads = [
            ExistingItemLineCreate(
                line_type=ProcurementLineType.EXISTING_ITEM,
                item_id=item_id,
                quantity=1,
            )
            for item_id in selected
        ]

        db.expire_all()

        async with captured_statements(db) as statements:
            rows = await _prepare_lines(
                db,
                payloads,
                uuid.uuid4(),
            )

        counts[size] = len(statements)

        assert len(rows) == size

        assert [row.catalog_item_id for row in rows] == selected

        assert [row.line_no for row in rows] == list(range(1, size + 1))

        for row in rows:
            item_id = row.catalog_item_id
            assert item_id is not None

            assert row.expected_identity_signature == signatures[item_id]

            assert row.display_snapshot["attributes"]["color"] == expected_colors[item_id]

    print(
        f"CP06_DISTINCT_EXISTING_COUNTS={counts}",
        flush=True,
    )

    assert counts[100] <= counts[1] + 6, counts
    assert counts[500] <= counts[1] + 6, counts


async def test_prepare_lines_500_mixed_proposed_items(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    suffix = uuid.uuid4().hex[:10]

    manufacturers = [
        Manufacturer(
            id=uuid.uuid4(),
            name=f"CP06 Alpha {suffix}",
            normalized_name=f"cp06 alpha {suffix}",
        ),
        Manufacturer(
            id=uuid.uuid4(),
            name=f"CP06 Beta {suffix}",
            normalized_name=f"cp06 beta {suffix}",
        ),
    ]

    db.add_all(manufacturers)
    await db.flush()

    first_id = manufacturers[0].id
    second_id = manufacturers[1].id

    cable_a = cable_payload()
    cable_b = cable_payload(
        fiber="SMF",
        fiber_category="OS2",
        length_m="7.5",
    )

    templates = [
        ItemCreate(
            category_key="optical_patch_cord",
            manufacturer_id=first_id,
            name="CP06 MMF patch cord",
            model="OM4-5",
            attributes=cable_a.attributes,
        ),
        ItemCreate(
            category_key="optical_splitter",
            manufacturer_id=second_id,
            name="CP06 splitter 1",
            model="SPLIT-12",
            attributes={
                "type": "PLC",
                "configuration": "1x2",
                "fiber": "SMF",
                "wavelength": "1310/1550 nm",
                "connector": "LC/UPC",
                "split_ratio": "1:2",
                "construction": "Module",
            },
        ),
        ItemCreate(
            category_key="optical_patch_cord",
            manufacturer_id=second_id,
            name="CP06 SMF patch cord",
            model="OS2-75",
            attributes=cable_b.attributes,
        ),
        ItemCreate(
            category_key="optical_splitter",
            manufacturer_id=first_id,
            name="CP06 splitter 2",
            model="SPLIT-14",
            attributes={
                "type": "PLC",
                "configuration": "1x4",
                "fiber": "SMF",
                "wavelength": "1550 nm",
                "connector": "SC/APC",
                "split_ratio": "1:4",
                "construction": "Cassette",
            },
        ),
    ]

    assert len({p.category_key for p in templates}) == 2
    assert len({p.manufacturer_id for p in templates}) == 2

    expected = [await validate_item_create_payload(db, payload) for payload in templates]

    counts: dict[int, int] = {}

    for size in (1, 100, 500):
        payloads = [
            ProposedItemLineCreate(
                line_type=ProcurementLineType.PROPOSED_ITEM,
                category_key=template.category_key,
                manufacturer_id=template.manufacturer_id,
                name=template.name,
                model=template.model,
                attributes=dict(template.attributes),
                quantity=1,
            )
            for template in (templates[index % len(templates)] for index in range(size))
        ]

        db.expire_all()

        async with captured_statements(db) as statements:
            rows = await _prepare_lines(
                db,
                payloads,
                uuid.uuid4(),
            )

        counts[size] = len(statements)

        assert len(rows) == size

        assert [row.line_no for row in rows] == list(range(1, size + 1))

        for index, row in enumerate(rows):
            reference = expected[index % len(expected)]

            expected_attributes = {
                key: (str(value) if isinstance(value, Decimal) else value)
                for key, value in reference.attributes.items()
            }

            assert row.line_type == ProcurementLineType.PROPOSED_ITEM
            assert row.catalog_item_id is None
            assert row.expected_identity_signature == (reference.identity_signature)

            snapshot = row.display_snapshot

            assert snapshot["category_key"] == reference.category.key
            assert snapshot["category_name"] == (reference.category.display_name)
            assert snapshot["manufacturer_id"] == (
                str(reference.manufacturer.id) if reference.manufacturer is not None else None
            )
            assert snapshot["manufacturer_name"] == (
                reference.manufacturer.name if reference.manufacturer is not None else None
            )
            assert snapshot["name"] == reference.name
            assert snapshot["model"] == reference.model
            assert snapshot["attributes"] == expected_attributes

    print(
        f"CP06_MIXED_PROPOSED_COUNTS={counts}",
        flush=True,
    )

    assert counts[100] <= counts[1] + 6, counts
    assert counts[500] <= counts[1] + 6, counts


async def test_procurement_summary_three_views_and_pagination(
    warehouse_db: AsyncSession,
) -> None:
    from types import SimpleNamespace

    from fastapi import Response

    from app.modules.procurement.api import get_requests
    from app.modules.procurement.enums import ProcurementStatus
    from app.modules.procurement.models import ProcurementRequest
    from app.modules.procurement.schemas import ProcurementRequestPageOut
    from tests.test_procurement_postgres import completed_procurement

    db = warehouse_db

    initiator, _ = await actor(db, UserRole.ADMIN)
    manager_a, _ = await actor(db, UserRole.MANAGER)
    manager_b, _ = await actor(db, UserRole.MANAGER)

    initiator_id = initiator.id
    manager_a_id = manager_a.id
    manager_b_id = manager_b.id

    item_id = await create_item(db, cable_payload())

    expected_metadata: dict[uuid.UUID, tuple[uuid.UUID, int, int]] = {}

    for index in range(37):
        manager_id = manager_a_id if index < 35 else manager_b_id

        line_count = 2 if index == 0 else 1

        record = await create_request(
            db,
            ProcurementRequestCreate(
                assigned_manager_user_id=manager_id,
                general_comment="CP06 summary pagination",
                client_request_id=uuid.uuid4().hex,
                lines=[
                    ExistingItemLineCreate(
                        line_type=ProcurementLineType.EXISTING_ITEM,
                        item_id=item_id,
                        quantity=1,
                    )
                    for _ in range(line_count)
                ],
            ),
            actor_user_id=initiator_id,
            settings=Settings(app_env="test"),
        )

        expected_metadata[record.request.id] = (
            record.request.current_revision_id,
            record.current_revision.revision_number,
            record.current_revision.line_count,
        )

    (
        _completed_initiator,
        _completed_manager,
        _completed_senior,
        _completed_item,
        _completed_location,
        completed,
    ) = await completed_procurement(db)

    completed_id = completed.request.id

    expected_metadata[completed_id] = (
        completed.request.current_revision_id,
        completed.current_revision.revision_number,
        completed.current_revision.line_count,
    )

    await db.flush()

    active_expected = list(
        (
            await db.scalars(
                select(ProcurementRequest.id)
                .where(ProcurementRequest.status != ProcurementStatus.COMPLETED)
                .order_by(
                    ProcurementRequest.created_at.desc(),
                    ProcurementRequest.id.desc(),
                )
            )
        ).all()
    )

    my_expected = list(
        (
            await db.scalars(
                select(ProcurementRequest.id)
                .where(
                    ProcurementRequest.assigned_manager_user_id == manager_a_id,
                    ProcurementRequest.status != ProcurementStatus.COMPLETED,
                )
                .order_by(
                    ProcurementRequest.created_at.desc(),
                    ProcurementRequest.id.desc(),
                )
            )
        ).all()
    )

    history_expected = list(
        (
            await db.scalars(
                select(ProcurementRequest.id)
                .where(ProcurementRequest.status == ProcurementStatus.COMPLETED)
                .order_by(
                    ProcurementRequest.created_at.desc(),
                    ProcurementRequest.id.desc(),
                )
            )
        ).all()
    )

    assert len(active_expected) == 37
    assert len(my_expected) == 35
    assert history_expected == [completed_id]

    async def check_page(
        view: str,
        limit: int,
        offset: int,
        expected_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        db.expire_all()

        response = Response()

        approved = SimpleNamespace(user=SimpleNamespace(id=manager_a_id))

        async with captured_statements(db) as statements:
            result = await get_requests(
                response=response,
                db=db,
                approved=approved,
                view=view,
                limit=limit,
                offset=offset,
            )

            encoded = result.model_dump_json()

            parsed = ProcurementRequestPageOut.model_validate_json(encoded)

        assert response.headers["Cache-Control"] == "no-store"

        assert parsed.total == len(expected_ids)
        assert parsed.limit == limit
        assert parsed.offset == offset

        actual_ids = [item.id for item in parsed.items]

        assert actual_ids == expected_ids[offset : offset + limit]

        for item in parsed.items:
            revision_id, revision_number, line_count = expected_metadata[item.id]

            assert item.current_revision_id == revision_id
            assert item.revision_number == revision_number
            assert item.line_count == line_count

            assert item.initiator.display_name
            assert item.assigned_manager.display_name

            assert item.initiator.display_name != str(item.initiator.id)

            assert item.assigned_manager.display_name != str(item.assigned_manager.id)

            if view == "my":
                assert item.assigned_manager.id == manager_a_id
                assert item.status != ProcurementStatus.COMPLETED

            if view == "active":
                assert item.status != ProcurementStatus.COMPLETED

            if view == "history":
                assert item.status == ProcurementStatus.COMPLETED

        history_sql = [
            statement
            for statement in statements
            if any(
                table in statement.lower()
                for table in (
                    "procurement_events",
                    "procurement_revision_lines",
                    "procurement_line_catalog_bindings",
                )
            )
        ]

        assert not history_sql, history_sql

        assert len(statements) <= 4, (
            f"view={view} offset={offset} queries={len(statements)} sql={statements}"
        )

        print(
            f"CP06_SUMMARY_VIEW={view} "
            f"OFFSET={offset} "
            f"SELECTS={len(statements)} "
            f"ITEMS={len(parsed.items)} "
            f"TOTAL={parsed.total}",
            flush=True,
        )

        return actual_ids

    active_first = await check_page("active", 30, 0, active_expected)

    active_second = await check_page("active", 30, 30, active_expected)

    assert len(active_first) == 30
    assert len(active_second) == 7

    assert not set(active_first).intersection(active_second)

    my_first = await check_page("my", 30, 0, my_expected)

    my_second = await check_page("my", 30, 30, my_expected)

    assert len(my_first) == 30
    assert len(my_second) == 5

    await check_page("history", 30, 0, history_expected)

    await check_page("active", 30, 100, active_expected)

    assert (
        expected_metadata[
            next(
                identifier for identifier, metadata in expected_metadata.items() if metadata[2] == 2
            )
        ][2]
        == 2
    )


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("missing", "catalog_item_not_found"),
        ("archived", "catalog_item_archived"),
    ],
)
async def test_cp06_prepare_lines_negative_existing_item(
    warehouse_db: AsyncSession,
    case: str,
    expected_code: str,
) -> None:
    db = warehouse_db

    if case == "missing":
        item_id = uuid.uuid4()
    else:
        item_id = await create_item(db, cable_payload())
        await set_item_archived(db, item_id, archived=True)

    payload = ExistingItemLineCreate(
        line_type=ProcurementLineType.EXISTING_ITEM,
        item_id=item_id,
        quantity=1,
    )

    with pytest.raises(ProcurementConflictError) as error:
        await _prepare_lines(
            db,
            [payload],
            uuid.uuid4(),
        )

    assert error.value.code == expected_code


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("unknown", "unknown_attribute"),
        ("required", "required_attribute_missing"),
    ],
)
async def test_cp06_prepare_lines_negative_proposed_item(
    warehouse_db: AsyncSession,
    case: str,
    expected_code: str,
) -> None:
    db = warehouse_db

    template = cable_payload()
    attributes = dict(template.attributes)

    if case == "unknown":
        attributes["cp06_nonexistent_attribute"] = "invalid"
    else:
        attributes.pop("fiber")

    payload = ProposedItemLineCreate(
        line_type=ProcurementLineType.PROPOSED_ITEM,
        category_key=template.category_key,
        manufacturer_id=template.manufacturer_id,
        name=template.name,
        model=template.model,
        attributes=attributes,
        quantity=1,
    )

    with pytest.raises(CatalogValidationError) as error:
        await _prepare_lines(
            db,
            [payload],
            uuid.uuid4(),
        )

    assert error.value.code == expected_code


async def test_cp06_prepare_lines_negative_input_order(
    warehouse_db: AsyncSession,
) -> None:
    db = warehouse_db

    template = cable_payload()

    invalid_attributes = dict(template.attributes)
    invalid_attributes["cp06_nonexistent_attribute"] = "invalid"

    invalid_proposed = ProposedItemLineCreate(
        line_type=ProcurementLineType.PROPOSED_ITEM,
        category_key=template.category_key,
        manufacturer_id=template.manufacturer_id,
        name=template.name,
        model=template.model,
        attributes=invalid_attributes,
        quantity=1,
    )

    missing_existing = ExistingItemLineCreate(
        line_type=ProcurementLineType.EXISTING_ITEM,
        item_id=uuid.uuid4(),
        quantity=1,
    )

    with pytest.raises(ProcurementConflictError) as first_error:
        await _prepare_lines(
            db,
            [missing_existing, invalid_proposed],
            uuid.uuid4(),
        )

    assert first_error.value.code == "catalog_item_not_found"

    with pytest.raises(CatalogValidationError) as second_error:
        await _prepare_lines(
            db,
            [invalid_proposed, missing_existing],
            uuid.uuid4(),
        )

    assert second_error.value.code == "unknown_attribute"

    print(
        "CP06_NEGATIVE_ERROR_ORDER=PASS",
        flush=True,
    )
