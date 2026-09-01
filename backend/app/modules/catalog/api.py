from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError

from app.modules.auth.dependencies import Admin, Approved, DbSession
from app.modules.catalog.enums import ItemStatus
from app.modules.catalog.models import Category, CategoryAttribute, Manufacturer
from app.modules.catalog.schemas import (
    CategoryAttributeOut,
    CategoryDetailOut,
    CategorySummaryOut,
    DuplicateCandidateOut,
    DuplicateCheckOut,
    DuplicateCheckRequest,
    ItemCategoryOut,
    ItemCreate,
    ItemListOut,
    ItemManufacturerOut,
    ItemOut,
    ItemPatch,
    ManufacturerCreate,
    ManufacturerListOut,
    ManufacturerOut,
)
from app.modules.catalog.service import (
    CatalogConflictError,
    CatalogError,
    CatalogNotFoundError,
    CatalogSchemaError,
    ItemRecord,
    check_duplicate_candidates,
    create_item,
    create_manufacturer,
    get_category_record,
    get_item_record,
    list_categories,
    list_items,
    list_manufacturers,
    set_item_archived,
    update_item,
)

read_router = APIRouter(prefix="/api/catalog", tags=["catalog"])
admin_router = APIRouter(prefix="/api/admin/catalog", tags=["admin-catalog"])


def _raise_catalog_error(error: CatalogError) -> NoReturn:
    if isinstance(error, CatalogNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
        message = str(error)
    elif isinstance(error, CatalogConflictError):
        status_code = status.HTTP_409_CONFLICT
        message = str(error)
    elif isinstance(error, CatalogSchemaError):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        message = "catalog schema configuration is invalid"
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        message = str(error)
    raise HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": message},
    ) from error


def _raise_integrity_conflict(error: IntegrityError) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "catalog_conflict",
            "message": "catalog data conflicts with an existing record",
        },
    ) from error


def _category_summary(category: Category) -> CategorySummaryOut:
    return CategorySummaryOut(
        id=category.id,
        key=category.key,
        display_name=category.display_name,
        description=category.description,
        default_accounting_mode=category.default_accounting_mode,
        sort_order=category.sort_order,
        is_system=category.is_system,
    )


def _category_attribute(attribute: CategoryAttribute) -> CategoryAttributeOut:
    return CategoryAttributeOut(
        id=attribute.id,
        key=attribute.key,
        label=attribute.label,
        data_type=attribute.data_type,
        unit=attribute.unit,
        required=attribute.required,
        filterable=attribute.filterable,
        searchable=attribute.searchable,
        card_visible=attribute.card_visible,
        detail_visible=attribute.detail_visible,
        table_visible=attribute.table_visible,
        excel_visible=attribute.excel_visible,
        sort_order=attribute.sort_order,
        filter_type=attribute.filter_type,
        allowed_values=attribute.allowed_values,
        validation_metadata=attribute.validation_metadata,
        is_system=attribute.is_system,
    )


def _manufacturer_out(manufacturer: Manufacturer) -> ManufacturerOut:
    return ManufacturerOut(
        id=manufacturer.id,
        name=manufacturer.name,
        created_at=manufacturer.created_at,
        updated_at=manufacturer.updated_at,
    )


def _item_out(record: ItemRecord) -> ItemOut:
    item = record.item
    manufacturer = record.manufacturer
    return ItemOut(
        id=item.id,
        category=ItemCategoryOut(
            id=record.category.id,
            key=record.category.key,
            display_name=record.category.display_name,
        ),
        manufacturer=(
            ItemManufacturerOut(
                id=manufacturer.id,
                name=manufacturer.name,
            )
            if manufacturer is not None
            else None
        ),
        name=item.name,
        model=item.model,
        manufacturer_part_number=item.manufacturer_part_number,
        internal_code=item.internal_code,
        description=item.description,
        accounting_mode=item.accounting_mode,
        status=item.status,
        comment=item.comment,
        datasheet_url=item.datasheet_url,
        technical_data_source=item.technical_data_source,
        archived_at=item.archived_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        attributes=record.attributes,
    )


async def _load_item_out(db: DbSession, item_id: UUID) -> ItemOut:
    try:
        return _item_out(await get_item_record(db, item_id))
    except CatalogError as error:
        _raise_catalog_error(error)


@read_router.get("/categories", response_model=list[CategorySummaryOut])
async def get_categories(
    db: DbSession,
    _approved: Approved,
) -> list[CategorySummaryOut]:
    return [_category_summary(category) for category in await list_categories(db)]


@read_router.get(
    "/categories/{category_key}",
    response_model=CategoryDetailOut,
)
async def get_category(
    category_key: str,
    db: DbSession,
    _approved: Approved,
) -> CategoryDetailOut:
    try:
        record = await get_category_record(db, category_key)
    except CatalogError as error:
        _raise_catalog_error(error)
    summary = _category_summary(record.category)
    return CategoryDetailOut(
        **summary.model_dump(),
        attributes=[
            _category_attribute(attribute) for attribute in record.attributes
        ],
    )


@read_router.get("/manufacturers", response_model=ManufacturerListOut)
async def get_manufacturers(
    db: DbSession,
    _approved: Approved,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ManufacturerListOut:
    page = await list_manufacturers(db, limit=limit, offset=offset)
    return ManufacturerListOut(
        items=[_manufacturer_out(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@read_router.get("/items", response_model=ItemListOut)
async def get_items(
    db: DbSession,
    _approved: Approved,
    category: Annotated[str | None, Query(max_length=64)] = None,
    item_status: Annotated[ItemStatus, Query(alias="status")] = ItemStatus.ACTIVE,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ItemListOut:
    try:
        page = await list_items(
            db,
            category_key=category,
            item_status=item_status,
            limit=limit,
            offset=offset,
        )
    except CatalogError as error:
        _raise_catalog_error(error)
    return ItemListOut(
        items=[_item_out(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@read_router.get("/items/{item_id}", response_model=ItemOut)
async def get_item(
    item_id: UUID,
    db: DbSession,
    _approved: Approved,
) -> ItemOut:
    return await _load_item_out(db, item_id)


@admin_router.post(
    "/manufacturers",
    response_model=ManufacturerOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_manufacturer(
    payload: ManufacturerCreate,
    db: DbSession,
    _admin: Admin,
) -> ManufacturerOut:
    try:
        manufacturer = await create_manufacturer(db, payload)
        await db.commit()
    except CatalogError as error:
        await db.rollback()
        _raise_catalog_error(error)
    except IntegrityError as error:
        await db.rollback()
        _raise_integrity_conflict(error)
    return _manufacturer_out(manufacturer)


@admin_router.post(
    "/items/check-duplicates",
    response_model=DuplicateCheckOut,
)
async def post_duplicate_check(
    payload: DuplicateCheckRequest,
    db: DbSession,
    _admin: Admin,
) -> DuplicateCheckOut:
    try:
        candidates = await check_duplicate_candidates(db, payload)
    except CatalogError as error:
        _raise_catalog_error(error)
    return DuplicateCheckOut(
        candidates=[
            DuplicateCandidateOut(
                item_id=candidate.item.id,
                name=candidate.item.name,
                model=candidate.item.model,
                manufacturer_id=candidate.item.manufacturer_id,
                manufacturer_name=(
                    candidate.manufacturer.name
                    if candidate.manufacturer is not None
                    else None
                ),
                manufacturer_part_number=(
                    candidate.item.manufacturer_part_number
                ),
                reason=candidate.reason,
            )
            for candidate in candidates
        ]
    )


@admin_router.post(
    "/items",
    response_model=ItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_item(
    payload: ItemCreate,
    db: DbSession,
    _admin: Admin,
) -> ItemOut:
    try:
        item_id = await create_item(db, payload)
        await db.commit()
    except CatalogError as error:
        await db.rollback()
        _raise_catalog_error(error)
    except IntegrityError as error:
        await db.rollback()
        _raise_integrity_conflict(error)
    return await _load_item_out(db, item_id)


@admin_router.patch("/items/{item_id}", response_model=ItemOut)
async def patch_item(
    item_id: UUID,
    payload: ItemPatch,
    db: DbSession,
    _admin: Admin,
) -> ItemOut:
    try:
        await update_item(
            db,
            item_id,
            payload,
            fields_set=set(payload.model_fields_set),
        )
        await db.commit()
    except CatalogError as error:
        await db.rollback()
        _raise_catalog_error(error)
    except IntegrityError as error:
        await db.rollback()
        _raise_integrity_conflict(error)
    return await _load_item_out(db, item_id)


@admin_router.post("/items/{item_id}/archive", response_model=ItemOut)
async def archive_item(
    item_id: UUID,
    db: DbSession,
    _admin: Admin,
) -> ItemOut:
    try:
        await set_item_archived(db, item_id, archived=True)
        await db.commit()
    except CatalogError as error:
        await db.rollback()
        _raise_catalog_error(error)
    return await _load_item_out(db, item_id)


@admin_router.post("/items/{item_id}/unarchive", response_model=ItemOut)
async def unarchive_item(
    item_id: UUID,
    db: DbSession,
    _admin: Admin,
) -> ItemOut:
    try:
        await set_item_archived(db, item_id, archived=False)
        await db.commit()
    except CatalogError as error:
        await db.rollback()
        _raise_catalog_error(error)
    return await _load_item_out(db, item_id)
