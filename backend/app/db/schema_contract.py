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
        "trg_items_required_attributes",
        "enforce_item_required_attributes",
        True,
        True,
    ),
    CriticalTrigger(
        "item_attribute_values",
        "trg_item_attribute_values_required_attributes",
        "enforce_item_attribute_required_completeness",
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


def critical_trigger_contract_sql() -> str:
    values = ",\n".join(
        (
            f"('{trigger.table_name}', "
            f"'{trigger.trigger_name}', "
            f"'{trigger.function_name}', "
            f"{str(trigger.deferrable).lower()}, "
            f"{str(trigger.initially_deferred).lower()})"
        )
        for trigger in CRITICAL_DB_TRIGGERS
    )

    return f"""
        WITH expected(
            table_name,
            trigger_name,
            function_name,
            is_deferrable,
            is_initially_deferred
        ) AS (
            VALUES
            {values}
        ),
        actual AS (
            SELECT
                c.relname AS table_name,
                t.tgname AS trigger_name,
                p.proname AS function_name,
                t.tgdeferrable AS is_deferrable,
                t.tginitdeferred AS is_initially_deferred
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
        )
        SELECT EXISTS (
            SELECT 1
            FROM expected e
            LEFT JOIN actual a
              ON a.table_name = e.table_name
             AND a.trigger_name = e.trigger_name
            WHERE a.trigger_name IS NULL
               OR a.function_name <> e.function_name
               OR a.is_deferrable <> e.is_deferrable
               OR a.is_initially_deferred
                  <> e.is_initially_deferred
        )
    """
