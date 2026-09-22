from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

# Validate required PostgreSQL invariants, not merely schema column names.
# Catalog introspection is read-only and uses no application-table privileges.
# Wrong table/function, disabled trigger, or wrong deferral/row mode fails closed.
_CRITICAL_DB_GUARDS_SQL = """
WITH required_functions(signature) AS (
    VALUES
            ('public.catalog_normalize_comparison(text)'),
            ('public.catalog_identity_text(text)'),
            ('public.catalog_decimal_identity(numeric)'),
            ('public.catalog_item_signature(uuid)'),
            ('public.assert_catalog_item_identity(uuid)')
),
required_triggers(table_name, trigger_name, function_signature, deferred, row_level) AS (
    VALUES
            (
                'public.procurement_revisions',
                'trg_procurement_revisions_append_only',
                'public.reject_procurement_immutable_mutation()',
                false, false
            ),
            (
                'public.procurement_revision_lines',
                'trg_procurement_revision_lines_append_only',
                'public.reject_procurement_immutable_mutation()',
                false, false
            ),
            (
                'public.procurement_line_catalog_bindings',
                'trg_procurement_line_catalog_bindings_append_only',
                'public.reject_procurement_immutable_mutation()',
                false, false
            ),
            (
                'public.procurement_events',
                'trg_procurement_events_append_only',
                'public.reject_procurement_immutable_mutation()',
                false, false
            ),
            (
                'public.procurement_requests',
                'trg_procurement_current_revision',
                'public.validate_procurement_current_revision()',
                true, true
            ),
            (
                'public.movements',
                'trg_movements_protect_procurement_receipt',
                'public.protect_procurement_receipt_movement()',
                false, true
            ),
            (
                'public.procurement_revision_lines',
                'trg_procurement_revision_lines_sealed_insert',
                'public.protect_procurement_revision_line_insert()',
                false, true
            ),
            (
                'public.procurement_events',
                'trg_procurement_events_validate_revision_publication',
                'public.validate_procurement_revision_publication()',
                false, true
            ),
            (
                'public.procurement_requests',
                'trg_procurement_requests_protect_final_movement',
                'public.protect_procurement_final_movement_binding()',
                false, true
            ),
            (
                'public.users',
                'trg_users_require_access_audit',
                'public.enforce_user_access_audit_coupling()',
                true, true
            ),
            (
                'public.users',
                'trg_users_require_role_audit',
                'public.enforce_user_role_audit_coupling()',
                true, true
            ),
            (
                'public.items',
                'trg_items_required_attributes',
                'public.enforce_item_required_attributes()',
                true, true
            ),
            (
                'public.item_attribute_values',
                'trg_item_attribute_values_required_attributes',
                'public.enforce_item_attribute_required_completeness()',
                true, true
            ),
            (
                'public.category_attributes',
                'trg_category_attributes_required_attributes',
                'public.enforce_category_required_attributes()',
                true, true
            ),
            (
                'public.user_item_custody_balances',
                'trg_user_item_custody_validate_holder',
                'public.enforce_custody_holder_eligibility()',
                false, true
            ),
            (
                'public.users',
                'trg_users_validate_custody_eligibility',
                'public.enforce_user_custody_eligibility()',
                true, true
            ),
            (
                'public.items',
                'trg_items_lock_identity',
                'public.lock_catalog_item_identity()',
                false, true
            ),
            (
                'public.item_attribute_values',
                'trg_item_attribute_values_lock_identity',
                'public.lock_catalog_item_attribute_identity()',
                false, true
            ),
            (
                'public.items',
                'trg_items_validate_identity',
                'public.validate_catalog_item_identity()',
                true, true
            ),
            (
                'public.item_attribute_values',
                'trg_item_attribute_values_validate_identity',
                'public.validate_catalog_item_attribute_identity()',
                true, true
            )
)
SELECT
    NOT EXISTS (
        SELECT 1 FROM required_functions AS requirement
        WHERE pg_catalog.to_regprocedure(requirement.signature) IS NULL
    )
    AND NOT EXISTS (
        SELECT 1
        FROM required_triggers AS requirement
        LEFT JOIN pg_catalog.pg_trigger AS actual
          ON actual.tgrelid = pg_catalog.to_regclass(requirement.table_name)
         AND actual.tgname = requirement.trigger_name
         AND NOT actual.tgisinternal
         AND actual.tgenabled IN ('O', 'A')
         AND actual.tgfoid = pg_catalog.to_regprocedure(requirement.function_signature)
         AND actual.tgdeferrable = requirement.deferred
         AND actual.tginitdeferred = requirement.deferred
         AND ((actual.tgtype & 1) <> 0) = requirement.row_level
        WHERE actual.oid IS NULL
    )
"""

class DatabaseUnavailableError(RuntimeError):
    """База данных недоступна для обслуживания запросов."""


async def ensure_database_ready(engine: AsyncEngine) -> None:
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(
                    "SELECT u.role, u.access_status, s.expires_at, i.identity_signature, "
                    "m.journal_seq, m.custody_user_id, ml.quantity, b.quantity, "
                    "c.user_id, c.item_id, c.quantity, "
                    "ua.actor_user_id, ua.target_user_id, "
                    "ua.before_access_status, ua.after_access_status, ua.occurred_at, "
                    "ur.actor_user_id, ur.target_user_id, "
                    "ur.before_role, ur.after_role, ur.occurred_at, "
                    "pr.state_version, pr.current_revision_id, "
                    "prl.expected_identity_signature, "
                    "pe.event_type, eo.status "
                    "FROM public.users u, public.auth_sessions s, public.items i, "
                    "public.movements m, public.movement_lines ml, public.stock_balances b, "
                    "public.user_item_custody_balances c, "
                    "public.user_access_events ua, public.user_role_events ur, "
                    "public.procurement_requests pr, public.procurement_events pe, "
                    "public.procurement_revision_lines prl, "
                    "public.email_outbox eo "
                    "WHERE false"
                )
            )
            guards = await connection.execute(text(_CRITICAL_DB_GUARDS_SQL))
            if guards.scalar_one() is not True:
                raise DatabaseUnavailableError("critical database invariants are unavailable")
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        raise DatabaseUnavailableError from exc
