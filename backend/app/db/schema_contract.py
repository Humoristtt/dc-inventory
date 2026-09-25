from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CriticalTrigger:
    table_name: str
    trigger_name: str
    function_name: str
    deferrable: bool = False
    initially_deferred: bool = False


CRITICAL_DB_TRIGGERS = (
    CriticalTrigger(
        "categories",
        "trg_categories_hierarchy",
        "validate_v2_category",
    ),
    CriticalTrigger(
        "category_attributes",
        "trg_category_attributes_leaf",
        "validate_v2_leaf",
    ),
    CriticalTrigger(
        "category_attributes",
        "trg_category_attributes_required_attributes",
        "enforce_category_required_attributes",
        True,
        True,
    ),
    CriticalTrigger(
        "items",
        "trg_items_leaf",
        "validate_v2_leaf",
    ),
    CriticalTrigger(
        "items",
        "trg_items_lock_identity",
        "lock_catalog_item_identity",
    ),
    CriticalTrigger(
        "items",
        "trg_items_required_attributes",
        "enforce_item_required_attributes",
        True,
        True,
    ),
    CriticalTrigger(
        "items",
        "trg_items_validate_identity",
        "validate_catalog_item_identity",
        True,
        True,
    ),
    CriticalTrigger(
        "item_attribute_values",
        "trg_item_attribute_values_lock_identity",
        "lock_catalog_item_attribute_identity",
    ),
    CriticalTrigger(
        "item_attribute_values",
        "trg_item_attribute_values_validate_data_type",
        "validate_item_attribute_value_data_type",
    ),
    CriticalTrigger(
        "item_attribute_values",
        "trg_item_attribute_values_required_attributes",
        "enforce_item_attribute_required_completeness",
        True,
        True,
    ),
    CriticalTrigger(
        "item_attribute_values",
        "trg_item_attribute_values_validate_identity",
        "validate_catalog_item_attribute_identity",
        True,
        True,
    ),
    CriticalTrigger(
        "movement_lines",
        "trg_movement_lines_append_only",
        "reject_warehouse_history_mutation",
    ),
    CriticalTrigger(
        "movement_lines",
        "trg_movement_lines_append_only_truncate",
        "reject_warehouse_history_mutation",
    ),
    CriticalTrigger(
        "movement_lines",
        "trg_movement_lines_validate_correction",
        "validate_warehouse_correction_line",
    ),
    CriticalTrigger(
        "movement_lines",
        "trg_movement_lines_validate_line_count",
        "validate_warehouse_movement_line_count",
        True,
        True,
    ),
    CriticalTrigger(
        "movements",
        "trg_movements_append_only",
        "reject_warehouse_history_mutation",
    ),
    CriticalTrigger(
        "movements",
        "trg_movements_append_only_truncate",
        "reject_warehouse_history_mutation",
    ),
    CriticalTrigger(
        "movements",
        "trg_movements_protect_procurement_receipt",
        "protect_procurement_receipt_movement",
    ),
    CriticalTrigger(
        "movements",
        "trg_movements_validate_correction",
        "validate_warehouse_correction_header",
    ),
    CriticalTrigger(
        "movements",
        "trg_movements_validate_custody",
        "validate_movement_custody",
    ),
    CriticalTrigger(
        "movements",
        "trg_movements_validate_line_count",
        "validate_warehouse_movement_line_count",
        True,
        True,
    ),
    CriticalTrigger(
        "procurement_events",
        "trg_procurement_events_append_only",
        "reject_procurement_immutable_mutation",
    ),
    CriticalTrigger(
        "procurement_events",
        "trg_procurement_events_validate_revision_publication",
        "validate_procurement_revision_publication",
    ),
    CriticalTrigger(
        "procurement_line_catalog_bindings",
        "trg_procurement_line_catalog_bindings_append_only",
        "reject_procurement_immutable_mutation",
    ),
    CriticalTrigger(
        "procurement_requests",
        "trg_procurement_current_revision",
        "validate_procurement_current_revision",
        True,
        True,
    ),
    CriticalTrigger(
        "procurement_requests",
        "trg_procurement_requests_protect_final_movement",
        "protect_procurement_final_movement_binding",
    ),
    CriticalTrigger(
        "procurement_revision_lines",
        "trg_procurement_revision_lines_append_only",
        "reject_procurement_immutable_mutation",
    ),
    CriticalTrigger(
        "procurement_revision_lines",
        "trg_procurement_revision_lines_sealed_insert",
        "protect_procurement_revision_line_insert",
    ),
    CriticalTrigger(
        "procurement_revisions",
        "trg_procurement_revisions_append_only",
        "reject_procurement_immutable_mutation",
    ),
    CriticalTrigger(
        "user_access_events",
        "trg_user_access_events_append_only",
        "reject_user_access_event_mutation",
    ),
    CriticalTrigger(
        "user_role_events",
        "trg_user_role_events_append_only",
        "reject_user_role_event_mutation",
    ),
    CriticalTrigger(
        "user_item_custody_balances",
        "trg_user_item_custody_validate_holder",
        "enforce_custody_holder_eligibility",
    ),
    CriticalTrigger(
        "users",
        "trg_users_require_access_audit",
        "enforce_user_access_audit_coupling",
        True,
        True,
    ),
    CriticalTrigger(
        "users",
        "trg_users_require_role_audit",
        "enforce_user_role_audit_coupling",
        True,
        True,
    ),
    CriticalTrigger(
        "users",
        "trg_users_validate_custody_eligibility",
        "enforce_user_custody_eligibility",
        True,
        True,
    ),
)

CRITICAL_DB_FUNCTIONS = (
    "assert_catalog_item_identity",
    "catalog_decimal_identity",
    "catalog_identity_text",
    "catalog_item_signature",
    "catalog_normalize_comparison",
)

CRITICAL_DB_COLLATIONS = (
    (
        "public",
        "dc_inventory_unicode_fast",
        "b",
        "PG_UNICODE_FAST",
        True,
    ),
)


def critical_trigger_contract_sql() -> str:
    trigger_values = ",\n".join(
        (
            f"('{trigger.table_name}', "
            f"'{trigger.trigger_name}', "
            f"'{trigger.function_name}', "
            f"{str(trigger.deferrable).lower()}, "
            f"{str(trigger.initially_deferred).lower()})"
        )
        for trigger in CRITICAL_DB_TRIGGERS
    )

    function_values = ",\n".join(f"('{name}')" for name in CRITICAL_DB_FUNCTIONS)

    collation_values = ",\n".join(
        (
            f"('{schema_name}', "
            f"'{collation_name}', "
            f"'{provider_code}', "
            f"'{locale_name}', "
            f"{str(deterministic).lower()})"
        )
        for (
            schema_name,
            collation_name,
            provider_code,
            locale_name,
            deterministic,
        ) in CRITICAL_DB_COLLATIONS
    )

    return f"""
        WITH expected_triggers(
            table_name,
            trigger_name,
            function_name,
            is_deferrable,
            is_initially_deferred
        ) AS (
            VALUES
            {trigger_values}
        ),
        actual_triggers AS (
            SELECT
                c.relname AS table_name,
                t.tgname AS trigger_name,
                p.proname AS function_name,
                t.tgdeferrable AS is_deferrable,
                t.tginitdeferred
                    AS is_initially_deferred
            FROM pg_trigger t
            JOIN pg_class c
              ON c.oid = t.tgrelid
            JOIN pg_namespace n
              ON n.oid = c.relnamespace
            JOIN pg_proc p
              ON p.oid = t.tgfoid
            WHERE n.nspname = 'public'
              AND NOT t.tgisinternal
              AND t.tgenabled IN ('O', 'A')
        ),
        expected_functions(function_name) AS (
            VALUES
            {function_values}
        ),
        actual_functions AS (
            SELECT DISTINCT
                p.proname AS function_name
            FROM pg_proc p
            JOIN pg_namespace n
              ON n.oid = p.pronamespace
            WHERE n.nspname = 'public'
              AND p.prokind = 'f'
        ),
        expected_collations(
            schema_name,
            collation_name,
            provider_code,
            locale_name,
            deterministic
        ) AS (
            VALUES
            {collation_values}
        ),
        actual_collations AS (
            SELECT
                n.nspname AS schema_name,
                c.collname AS collation_name,
                c.collprovider::text AS provider_code,
                c.colllocale AS locale_name,
                c.collisdeterministic AS deterministic
            FROM pg_collation c
            JOIN pg_namespace n
              ON n.oid = c.collnamespace
        )
        SELECT
            EXISTS (
                SELECT 1
                FROM expected_triggers e
                LEFT JOIN actual_triggers a
                  ON a.table_name = e.table_name
                 AND a.trigger_name = e.trigger_name
                WHERE a.trigger_name IS NULL
                   OR a.function_name
                      <> e.function_name
                   OR a.is_deferrable
                      <> e.is_deferrable
                   OR a.is_initially_deferred
                      <> e.is_initially_deferred
            )
            OR EXISTS (
                SELECT 1
                FROM expected_functions e
                LEFT JOIN actual_functions a
                  ON a.function_name = e.function_name
                WHERE a.function_name IS NULL
            )
            OR EXISTS (
                SELECT 1
                FROM expected_collations e
                LEFT JOIN actual_collations a
                  ON a.schema_name = e.schema_name
                 AND a.collation_name = e.collation_name
                WHERE a.collation_name IS NULL
                   OR a.provider_code
                      <> e.provider_code
                   OR a.locale_name
                      <> e.locale_name
                   OR a.deterministic
                      <> e.deterministic
            )
    """
