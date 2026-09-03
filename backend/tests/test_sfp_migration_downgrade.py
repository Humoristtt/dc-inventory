from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "a2b3c4d5e6f7_refine_authoritative_sfp_metadata.py"
)


def _load_migration() -> ModuleType:
    spec = spec_from_file_location("sfp_refinement_migration", MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load SFP refinement migration")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_downgrade_refuses_to_delete_existing_profile_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    connection = Mock()
    connection.execute.return_value.scalar_one_or_none.return_value = True
    execute = Mock()

    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(migration.op, "execute", execute)

    with pytest.raises(
        RuntimeError,
        match="Refusing destructive downgrade of a2b3c4d5e6f7",
    ):
        migration.downgrade()

    execute.assert_not_called()


def test_downgrade_without_profile_values_removes_only_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    connection = Mock()
    connection.execute.return_value.scalar_one_or_none.return_value = None
    execute = Mock()

    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    monkeypatch.setattr(migration.op, "execute", execute)

    migration.downgrade()

    assert execute.call_count == 2
    statements = [
        str(call.args[0])
        for call in execute.call_args_list
    ]
    assert all("item_attribute_values" not in statement for statement in statements)
    assert any("DELETE FROM category_attributes" in statement for statement in statements)
    assert any("UPDATE category_attributes" in statement for statement in statements)
